#!/usr/bin/env python3

import argparse
import os

from config_parser import GenedescConfigParser
from data_fetcher import WBRawDataFetcher, AGRRawDataFetcher
from descriptions_rules import *
from descriptions_writer import JsonGDWriter, GeneDesc, SingleDescStats


def main():
    parser = argparse.ArgumentParser(description="Generate gene descriptions for wormbase")
    parser.add_argument("-c", "--config-file", metavar="config_file", dest="config_file", type=str,
                        default="config.yml", help="configuration file")
    parser.add_argument("-C", "--use-cache", dest="use_cache", action="store_true", default=False,
                        help="Use cached source files from cache_location specified in config file. Download them from "
                             "raw_file_source (configured in config file) if not yet cached")
    parser.add_argument("-l", "--log-file", metavar="log_file", dest="log_file", type=str,
                        default="genedescriptions.log", help="path to the log file to generate")
    parser.add_argument("-L", "--log-level", dest="log_level", choices=['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                                                        'CRITICAL'], help="set the logging level")
    parser.add_argument("-v", "--output-version", metavar="version_number", dest="version_number", type=str,
                        help="release version number")

    args = parser.parse_args()

    conf_parser = GenedescConfigParser(args.config_file)

    logging.basicConfig(filename=args.log_file, level=args.log_level)

    cache_location = conf_parser.get_cache_location()
    species = conf_parser.get_wb_species()
    go_prepostfix_sentences_map = conf_parser.get_go_prepostfix_sentences_map()
    go_prepostfix_special_cases_sent_map = conf_parser.get_go_prepostfix_special_cases_sent_map()
    go_annotations_priority = conf_parser.get_go_annotations_priority()
    evidence_groups_priority_list = conf_parser.get_evidence_groups_priority_list()
    evidence_codes_groups_map = conf_parser.get_evidence_codes_groups_map()
    go_terms_exclusion_list = conf_parser.get_go_terms_exclusion_list()

    if conf_parser.get_data_fetcher() == "agr_data_fetcher":
        organisms_list = conf_parser.get_agr_organisms_to_process()
    else:
        organisms_list = conf_parser.get_wb_organisms_to_process()
    for organism in organisms_list:
        logging.info("processing organism " + organism)
        if conf_parser.get_data_fetcher() == "agr_data_fetcher":
            df = AGRRawDataFetcher(go_terms_exclusion_list=go_terms_exclusion_list,
                                   go_terms_replacement_dict=conf_parser.get_go_rename_terms(),
                                   raw_files_source=conf_parser.get_raw_file_sources(conf_parser.get_data_fetcher()),
                                   chebi_file_url=conf_parser.get_chebi_file_source(),
                                   release_version=conf_parser.get_release(conf_parser.get_data_fetcher()),
                                   main_file_name=conf_parser.get_agr_mod_property(organism, "main_files"),
                                   bgi_file_name=conf_parser.get_agr_mod_property(organism, "bgi_file"),
                                   go_annotations_file_name=conf_parser.get_agr_mod_property(organism,
                                                                                             "go_annotations"),
                                   organism_name=conf_parser.get_agr_mod_property(organism, "name"),
                                   cache_location=cache_location, use_cache=args.use_cache)
        else:
            df = WBRawDataFetcher(go_terms_exclusion_list=go_terms_exclusion_list,
                                  go_terms_replacement_dict=conf_parser.get_go_rename_terms(),
                                  raw_files_source=conf_parser.get_raw_file_sources(conf_parser.get_data_fetcher()),
                                  chebi_file_url=conf_parser.get_chebi_file_source(),
                                  release_version=conf_parser.get_release(conf_parser.get_data_fetcher()),
                                  species=organism,
                                  project_id=species[organism]["project_id"],
                                  cache_location=cache_location, use_cache=args.use_cache)

        df.load_go_data()
        desc_writer = JsonGDWriter()
        for gene in df.get_gene_data():
            logging.debug("processing gene " + gene.name)
            gene_desc = GeneDesc(gene_name=gene.name)
            sentences = generate_go_sentences(df.get_go_annotations(
                gene.id, priority_list=go_annotations_priority, desc_stats=gene_desc.stats),
                go_ontology=df.get_go_ontology(),
                go_slim_ontology=df.get_go_slim_ontology(),
                evidence_groups_priority_list=evidence_groups_priority_list,
                go_prepostfix_sentences_map=go_prepostfix_sentences_map,
                go_prepostfix_special_cases_sent_map=go_prepostfix_special_cases_sent_map,
                evidence_codes_groups_map=evidence_codes_groups_map, remove_parent_terms=True,
                merge_num_terms_threshold=conf_parser.get_go_merge_min_num_terms(),
                merge_min_distance_from_root=conf_parser.get_go_merge_min_distance_from_root(),
                merge_algorithm=conf_parser.get_go_merge_algorithm(),
                desc_stats=gene_desc.stats, go_terms_replacement_dict=conf_parser.get_go_rename_terms())
            if sentences:
                joined_sent = []
                func_sent = sentences.get_sentences(go_aspect='F', merge_groups_with_same_prefix=True,
                                                    keep_only_best_group=True, desc_stats=gene_desc.stats)
                proc_sent = sentences.get_sentences(go_aspect='P', merge_groups_with_same_prefix=True,
                                                    keep_only_best_group=True, desc_stats=gene_desc.stats)
                comp_sent = sentences.get_sentences(go_aspect='C', merge_groups_with_same_prefix=True,
                                                    keep_only_best_group=True, desc_stats=gene_desc.stats)
                exact_sent = []
                predicted_sent = []

                def group_sentence(sentence):
                    if sentence:
                        if sentence[0].prefix.startswith("predicted to"):
                            predicted_sent.append(sentence[0].text.replace("predicted to ", ""))
                        else:
                            exact_sent.append(sentence[0].text)
                group_sentence(func_sent)
                group_sentence(proc_sent)
                group_sentence(comp_sent)

                go_desc_exact = "; ".join(exact_sent)
                go_desc_predicted = "predicted to: " + "; ".join(predicted_sent)
                if go_desc_exact:
                    joined_sent.append(go_desc_exact)
                if go_desc_predicted != "predicted to: ":
                    joined_sent.append(go_desc_predicted)
                go_desc = "; ".join(joined_sent)
                if len(go_desc) > 0:
                    gene_desc.description = go_desc[0].upper() + go_desc[1:]
                else:
                    gene_desc.description = "No description available"
            else:
                gene_desc.description = "No description available"
            desc_writer.add_gene_desc(gene_desc)
        desc_writer.write(os.path.join(conf_parser.get_genedesc_output_dir(conf_parser.get_genedesc_writer()),
                                       organism + "_with_stats.json"), pretty=True, include_single_gene_stats=True)
        desc_writer.write(os.path.join(conf_parser.get_genedesc_output_dir(conf_parser.get_genedesc_writer()),
                                       organism + "_no_stats.json"), pretty=True, include_single_gene_stats=False)


if __name__ == '__main__':
    main()
