"""
EPUB processing module for specialized e-book translation
"""
import os
import zipfile
import tempfile
from lxml import etree
from tqdm.auto import tqdm

from config import (
    NAMESPACES, IGNORED_TAGS_EPUB, CONTENT_BLOCK_TAGS_EPUB,
    DEFAULT_MODEL, MAIN_LINES_PER_CHUNK, API_ENDPOINT
)
from .text_processor import split_text_into_chunks_with_context
from .translator import translate_chunks


def _get_node_text_content_with_br_as_newline(node):
    """
    Extract text content from XML/HTML node with <br> handling
    
    Args:
        node: lxml element node
        
    Returns:
        str: Extracted text with <br> tags converted to newlines
    """
    parts = []
    if node.text:
        parts.append(node.text)

    for child in node:
        child_qname_str = child.tag
        br_xhtml_tag = etree.QName(NAMESPACES['xhtml'], 'br').text

        if child_qname_str == br_xhtml_tag:
            if parts and parts[-1].endswith('\n'):
                pass
            elif parts and parts[-1] == '\n':
                pass
            else:
                parts.append('\n')
        elif child_qname_str in CONTENT_BLOCK_TAGS_EPUB:
            if parts and parts[-1] and not parts[-1].endswith('\n'):
                parts.append('\n')
        else:
            parts.append(_get_node_text_content_with_br_as_newline(child))

        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def _collect_epub_translation_jobs_recursive(element, file_path_abs, jobs_list, chunk_size, log_callback=None):
    """
    Recursively collect translation jobs from EPUB elements
    
    Args:
        element: lxml element to process
        file_path_abs (str): Absolute file path
        jobs_list (list): List to append jobs to
        chunk_size (int): Target chunk size
        log_callback (callable): Logging callback
    """
    if element.tag in IGNORED_TAGS_EPUB:
        return

    if element.tag in CONTENT_BLOCK_TAGS_EPUB:
        text_content_for_chunking = _get_node_text_content_with_br_as_newline(element).strip()
        if text_content_for_chunking:
            sub_chunks = split_text_into_chunks_with_context(text_content_for_chunking, chunk_size)
            if not sub_chunks and text_content_for_chunking:
                sub_chunks = [{"context_before": "", "main_content": text_content_for_chunking, "context_after": ""}]

            if sub_chunks:
                jobs_list.append({
                    'element_ref': element,
                    'type': 'block_content',
                    'original_text_stripped': text_content_for_chunking,
                    'sub_chunks': sub_chunks,
                    'file_path': file_path_abs,
                    'translated_text': None
                })
    else:
        if element.text:
            original_text_content = element.text
            text_to_translate = original_text_content.strip()
            if text_to_translate:
                leading_space = original_text_content[:len(original_text_content) - len(original_text_content.lstrip())]
                trailing_space = original_text_content[len(original_text_content.rstrip()):]
                sub_chunks = split_text_into_chunks_with_context(text_to_translate, chunk_size)
                if not sub_chunks and text_to_translate:
                    sub_chunks = [{"context_before": "", "main_content": text_to_translate, "context_after": ""}]

                if sub_chunks:
                    jobs_list.append({
                        'element_ref': element,
                        'type': 'text',
                        'original_text_stripped': text_to_translate,
                        'sub_chunks': sub_chunks,
                        'leading_space': leading_space,
                        'trailing_space': trailing_space,
                        'file_path': file_path_abs,
                        'translated_text': None
                    })

    # Recursive processing of children
    for child in element:
        _collect_epub_translation_jobs_recursive(child, file_path_abs, jobs_list, chunk_size, log_callback)

    # Handle tail text for non-block elements
    if element.tag not in CONTENT_BLOCK_TAGS_EPUB and element.tail:
        original_tail_content = element.tail
        tail_to_translate = original_tail_content.strip()
        if tail_to_translate:
            leading_space_tail = original_tail_content[:len(original_tail_content) - len(original_tail_content.lstrip())]
            trailing_space_tail = original_tail_content[len(original_tail_content.rstrip()):]
            sub_chunks = split_text_into_chunks_with_context(tail_to_translate, chunk_size)
            if not sub_chunks and tail_to_translate:
                sub_chunks = [{"context_before": "", "main_content": tail_to_translate, "context_after": ""}]

            if sub_chunks:
                jobs_list.append({
                    'element_ref': element,
                    'type': 'tail',
                    'original_text_stripped': tail_to_translate,
                    'sub_chunks': sub_chunks,
                    'leading_space': leading_space_tail,
                    'trailing_space': trailing_space_tail,
                    'file_path': file_path_abs,
                    'translated_text': None
                })


async def translate_epub_file(input_filepath, output_filepath,
                              source_language="English", target_language="French",
                              model_name=DEFAULT_MODEL, chunk_target_lines_arg=MAIN_LINES_PER_CHUNK,
                              cli_api_endpoint=API_ENDPOINT,
                              progress_callback=None, log_callback=None, stats_callback=None,
                              check_interruption_callback=None, custom_instructions=""):
    """
    Translate an EPUB file
    
    Args:
        input_filepath (str): Path to input EPUB
        output_filepath (str): Path to output EPUB
        source_language (str): Source language
        target_language (str): Target language
        model_name (str): LLM model name
        chunk_target_lines_arg (int): Target lines per chunk
        cli_api_endpoint (str): API endpoint
        progress_callback (callable): Progress callback
        log_callback (callable): Logging callback
        stats_callback (callable): Statistics callback
        check_interruption_callback (callable): Interruption check callback
    """
    if not os.path.exists(input_filepath):
        err_msg = f"ERROR: Input EPUB file '{input_filepath}' not found."
        if log_callback: 
            log_callback("epub_input_file_not_found", err_msg)
        else: 
            print(err_msg)
        return

    all_translation_jobs = []
    parsed_xhtml_docs = {}

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Extract EPUB
            with zipfile.ZipFile(input_filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find OPF file
            opf_path = None
            for root_dir, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.opf'):
                        opf_path = os.path.join(root_dir, file)
                        break
                if opf_path: 
                    break
            if not opf_path: 
                raise FileNotFoundError("CRITICAL ERROR: content.opf not found in EPUB.")

            # Parse OPF
            opf_tree = etree.parse(opf_path)
            opf_root = opf_tree.getroot()

            manifest = opf_root.find('.//opf:manifest', namespaces=NAMESPACES)
            spine = opf_root.find('.//opf:spine', namespaces=NAMESPACES)
            if manifest is None or spine is None: 
                raise ValueError("CRITICAL ERROR: manifest or spine missing in EPUB.")

            # Get content files
            content_files_hrefs = []
            for itemref in spine.findall('.//opf:itemref', namespaces=NAMESPACES):
                idref = itemref.get('idref')
                item = manifest.find(f'.//opf:item[@id="{idref}"]', namespaces=NAMESPACES)
                if item is not None and item.get('media-type') in ['application/xhtml+xml', 'text/html'] and item.get('href'):
                    content_files_hrefs.append(item.get('href'))

            opf_dir = os.path.dirname(opf_path)

            # Phase 1: Collect translation jobs
            if log_callback: 
                log_callback("epub_phase1_start", "Phase 1: Collecting and splitting text from EPUB...")

            iterator_phase1 = tqdm(content_files_hrefs, desc="Analyzing EPUB files", unit="file") if not log_callback else content_files_hrefs
            for file_idx, content_href in enumerate(iterator_phase1):
                if progress_callback and len(content_files_hrefs) > 0:
                    progress_callback((file_idx / len(content_files_hrefs)) * 10)

                file_path_abs = os.path.normpath(os.path.join(opf_dir, content_href))
                if not os.path.exists(file_path_abs):
                    warn_msg = f"WARNING: EPUB file '{content_href}' not found at '{file_path_abs}', ignored."
                    if log_callback: 
                        log_callback("epub_content_file_not_found", warn_msg)
                    else: 
                        tqdm.write(warn_msg)
                    continue
                
                try:
                    with open(file_path_abs, 'r', encoding='utf-8') as f_chap:
                        chap_str_content = f_chap.read()

                    parser = etree.XMLParser(encoding='utf-8', recover=True, remove_blank_text=False)
                    doc_chap_root = etree.fromstring(chap_str_content.encode('utf-8'), parser)
                    parsed_xhtml_docs[file_path_abs] = doc_chap_root

                    body_el = doc_chap_root.find('.//{http://www.w3.org/1999/xhtml}body')
                    if body_el is not None:
                        _collect_epub_translation_jobs_recursive(body_el, file_path_abs, all_translation_jobs, chunk_target_lines_arg, log_callback)

                except etree.XMLSyntaxError as e_xml:
                    err_msg_xml = f"XML Syntax ERROR in '{content_href}': {e_xml}. Ignored."
                    if log_callback: 
                        log_callback("epub_xml_syntax_error", err_msg_xml)
                    else: 
                        tqdm.write(err_msg_xml)
                except Exception as e_chap:
                    err_msg_chap = f"ERROR Collecting chapter jobs '{content_href}': {e_chap}. Ignored."
                    if log_callback: 
                        log_callback("epub_collect_job_error", err_msg_chap)
                    else: 
                        tqdm.write(err_msg_chap)

            if not all_translation_jobs:
                info_msg_no_jobs = "No translatable text segments found in the EPUB."
                if log_callback: 
                    log_callback("epub_no_translatable_segments", info_msg_no_jobs)
                else: 
                    tqdm.write(info_msg_no_jobs)
                if progress_callback: 
                    progress_callback(100)
                return
            else:
                if log_callback: 
                    log_callback("epub_jobs_collected", f"{len(all_translation_jobs)} translatable segments collected.")

            if stats_callback and all_translation_jobs:
                stats_callback({'total_chunks': len(all_translation_jobs), 'completed_chunks': 0, 'failed_chunks': 0})

            # Phase 2: Translate
            if log_callback: 
                log_callback("epub_phase2_start", "\nPhase 2: Translating EPUB text segments...")

            last_successful_llm_context = ""
            completed_jobs_count = 0
            failed_jobs_count = 0

            iterator_phase2 = tqdm(all_translation_jobs, desc="Translating EPUB segments", unit="seg") if not log_callback else all_translation_jobs
            for job_idx, job in enumerate(iterator_phase2):
                if check_interruption_callback and check_interruption_callback():
                    if log_callback: 
                        log_callback("epub_translation_interrupted", f"EPUB translation process (job {job_idx+1}/{len(all_translation_jobs)}) interrupted by user signal.")
                    else: 
                        tqdm.write(f"\nEPUB translation interrupted by user at job {job_idx+1}/{len(all_translation_jobs)}.")
                    break

                if progress_callback and len(all_translation_jobs) > 0:
                    base_progress_phase2 = ((job_idx + 1) / len(all_translation_jobs)) * 90
                    progress_callback(10 + base_progress_phase2)

                # Translate sub-chunks for this job
                translated_parts = await translate_chunks(
                    job['sub_chunks'], source_language, target_language, 
                    model_name, cli_api_endpoint, None, log_callback, None, check_interruption_callback, custom_instructions
                )
                
                job['translated_text'] = "\n".join(translated_parts)
                
                if any("[TRANSLATION_ERROR" in part for part in translated_parts):
                    failed_jobs_count += 1
                else:
                    completed_jobs_count += 1

                if stats_callback and all_translation_jobs:
                    stats_callback({'completed_chunks': completed_jobs_count, 'failed_chunks': failed_jobs_count})

            if progress_callback: 
                progress_callback(100)

            # Phase 3: Apply translations
            if log_callback: 
                log_callback("epub_phase3_start", "\nPhase 3: Applying translations to EPUB files...")

            iterator_phase3 = tqdm(all_translation_jobs, desc="Updating EPUB content", unit="seg") if not log_callback else all_translation_jobs
            for job in iterator_phase3:
                if job.get('translated_text') is None: 
                    continue

                element = job['element_ref']
                translated_content = job['translated_text']

                if job['type'] == 'block_content':
                    element.text = translated_content
                    for child_node in list(element):
                        element.remove(child_node)
                elif job['type'] == 'text':
                    element.text = job['leading_space'] + translated_content + job['trailing_space']
                elif job['type'] == 'tail':
                    element.tail = job['leading_space'] + translated_content + job['trailing_space']

            # Update metadata
            metadata = opf_root.find('.//opf:metadata', namespaces=NAMESPACES)
            if metadata is not None:
                lang_el = metadata.find('.//dc:language', namespaces=NAMESPACES)
                if lang_el is not None: 
                    lang_el.text = target_language.lower()[:2]

            # Save OPF
            opf_tree.write(opf_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

            # Save XHTML files
            for file_path_abs, doc_root in parsed_xhtml_docs.items():
                try:
                    with open(file_path_abs, 'wb') as f_out:
                        f_out.write(etree.tostring(doc_root, encoding='utf-8', xml_declaration=True, pretty_print=True, method='xml'))
                except Exception as e_write:
                    err_msg_write = f"ERROR writing modified EPUB file '{file_path_abs}': {e_write}"
                    if log_callback: 
                        log_callback("epub_write_error", err_msg_write)
                    else: 
                        tqdm.write(err_msg_write)

            # Create output EPUB
            if log_callback: 
                log_callback("epub_zip_start", "\nCreating translated EPUB file...")

            with zipfile.ZipFile(output_filepath, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
                mimetype_path_abs = os.path.join(temp_dir, 'mimetype')
                if os.path.exists(mimetype_path_abs):
                    epub_zip.write(mimetype_path_abs, 'mimetype', compress_type=zipfile.ZIP_STORED)

                for root_path, _, files_in_root in os.walk(temp_dir):
                    for file_item in files_in_root:
                        if file_item != 'mimetype':
                            file_path_abs_for_zip = os.path.join(root_path, file_item)
                            arcname = os.path.relpath(file_path_abs_for_zip, temp_dir)
                            epub_zip.write(file_path_abs_for_zip, arcname)

            success_save_msg = f"Translated (Full/Partial) EPUB saved: '{output_filepath}'"
            if log_callback: 
                log_callback("epub_save_success", success_save_msg)
            else: 
                tqdm.write(success_save_msg)

        except Exception as e_epub:
            major_err_msg = f"MAJOR ERROR processing EPUB '{input_filepath}': {e_epub}"
            if log_callback:
                log_callback("epub_major_error", major_err_msg)
                import traceback
                log_callback("epub_major_error_traceback", traceback.format_exc())
            else:
                print(major_err_msg)
                import traceback
                traceback.print_exc()