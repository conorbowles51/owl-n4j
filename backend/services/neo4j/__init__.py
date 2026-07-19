"""
Neo4j service package — backward-compatible facade.

All routers import `from services.neo4j_service import neo4j_service`.
That module re-exports the facade created here, so no router changes needed.

Domain services can also be imported directly for new code:
    from services.neo4j.graph_service import graph_service
    from services.neo4j.financial_service import financial_service
"""

from services.neo4j.driver import driver, parse_json_field, safe_float
from services.neo4j.graph_service import graph_service
from services.neo4j.entity_service import entity_service
from services.neo4j.financial_service import financial_service
from services.neo4j.algorithm_service import algorithm_service
from services.neo4j.document_service import document_service
from services.neo4j.geo_service import geo_service
from services.neo4j.timeline_service import timeline_service
from services.neo4j.cellebrite_service import cellebrite_service, resolve_file_parents
from services.neo4j.graph_edit_service import graph_edit_service


class Neo4jServiceFacade:
    """
    Facade that delegates to focused domain services.

    Preserves the original neo4j_service interface so every existing
    `neo4j_service.some_method(...)` call keeps working unchanged.
    """

    # ── Driver-level ───────────────────────────────────────────────────
    close = staticmethod(driver.close)
    session = staticmethod(driver.session)
    run_cypher = staticmethod(driver.run_cypher)
    validate_cypher_batch = staticmethod(driver.validate_cypher_batch)
    execute_cypher_batch = staticmethod(driver.execute_cypher_batch)
    clear_graph = staticmethod(driver.clear_graph)
    delete_case_data = staticmethod(driver.delete_case_data)

    @property
    def _driver(self):
        """Backward-compatible access for older call sites."""
        return driver._driver

    # ── Graph visualization & search ───────────────────────────────────
    get_full_graph = staticmethod(graph_service.get_full_graph)
    get_existing_node_keys = staticmethod(graph_service.get_existing_node_keys)
    get_graph_structure = staticmethod(graph_service.get_graph_structure)
    get_node_with_neighbours = staticmethod(graph_service.get_node_with_neighbours)
    expand_nodes = staticmethod(graph_service.expand_nodes)
    get_node_details = staticmethod(graph_service.get_node_details)
    search_nodes = staticmethod(graph_service.search_nodes)
    get_graph_summary = staticmethod(graph_service.get_graph_summary)
    get_context_for_nodes = staticmethod(graph_service.get_context_for_nodes)

    # ── Entity management ──────────────────────────────────────────────
    pin_fact = staticmethod(entity_service.pin_fact)
    verify_insight = staticmethod(entity_service.verify_insight)
    find_similar_entities = staticmethod(entity_service.find_similar_entities)
    find_similar_entities_streaming = staticmethod(entity_service.find_similar_entities_streaming)
    delete_node = staticmethod(entity_service.delete_node)
    soft_delete_entity = staticmethod(entity_service.soft_delete_entity)
    list_recycled_entities = staticmethod(entity_service.list_recycled_entities)
    restore_recycled_entity = staticmethod(entity_service.restore_recycled_entity)
    permanently_delete_recycled = staticmethod(entity_service.permanently_delete_recycled)
    get_case_entity_summary = staticmethod(entity_service.get_case_entity_summary)
    batch_update_entities = staticmethod(graph_edit_service.batch_update_entities)
    update_graph_node = staticmethod(graph_edit_service.update_node)
    apply_geocoded_location = staticmethod(graph_edit_service.apply_geocoded_location)
    undo_location_relocation = staticmethod(graph_edit_service.undo_last_location_relocation)
    apply_location_correction = staticmethod(graph_edit_service.apply_geocoded_location)
    undo_last_location_correction = staticmethod(graph_edit_service.undo_last_location_relocation)
    update_geocoded_location = staticmethod(graph_edit_service.update_geocoded_location)
    get_graph_edit_schema = staticmethod(lambda: graph_edit_service.editable_schema)
    get_entities_for_insights = staticmethod(entity_service.get_entities_for_insights)
    save_entity_insights = staticmethod(entity_service.save_entity_insights)
    reject_entity_insight = staticmethod(entity_service.reject_entity_insight)
    get_all_pending_insights = staticmethod(entity_service.get_all_pending_insights)

    # ── Financial analysis ─────────────────────────────────────────────
    get_financial_transactions = staticmethod(financial_service.get_financial_transactions)
    get_financial_entities = staticmethod(financial_service.get_financial_entities)
    get_financial_summary = staticmethod(financial_service.get_financial_summary)
    get_financial_volume_over_time = staticmethod(financial_service.get_financial_volume_over_time)
    update_transaction_category = staticmethod(financial_service.update_transaction_category)
    update_transaction_from_to = staticmethod(financial_service.update_transaction_from_to)
    get_financial_categories = staticmethod(financial_service.get_financial_categories)
    create_financial_category = staticmethod(financial_service.create_financial_category)
    update_transaction_details = staticmethod(financial_service.update_transaction_details)
    batch_update_from_to = staticmethod(financial_service.batch_update_from_to)
    update_transaction_amount = staticmethod(financial_service.update_transaction_amount)
    link_sub_transaction = staticmethod(financial_service.link_sub_transaction)
    unlink_sub_transaction = staticmethod(financial_service.unlink_sub_transaction)
    get_transaction_children = staticmethod(financial_service.get_transaction_children)

    # ── Algorithms ─────────────────────────────────────────────────────
    get_shortest_paths_subgraph = staticmethod(algorithm_service.get_shortest_paths_subgraph)
    get_pagerank_subgraph = staticmethod(algorithm_service.get_pagerank_subgraph)
    get_louvain_communities = staticmethod(algorithm_service.get_louvain_communities)
    get_betweenness_centrality = staticmethod(algorithm_service.get_betweenness_centrality)

    # ── Documents ──────────────────────────────────────────────────────
    get_document_summary = staticmethod(document_service.get_document_summary)
    get_document_summaries_batch = staticmethod(document_service.get_document_summaries_batch)
    get_folder_summary = staticmethod(document_service.get_folder_summary)
    get_transcription_translation = staticmethod(document_service.get_transcription_translation)
    find_document_node = staticmethod(document_service.find_document_node)
    find_exclusive_entities = staticmethod(document_service.find_exclusive_entities)
    delete_document_and_exclusive_entities = staticmethod(document_service.delete_document_and_exclusive_entities)

    # ── Geo ────────────────────────────────────────────────────────────
    get_entities_with_locations = staticmethod(geo_service.get_entities_with_locations)
    get_locations_needing_review = staticmethod(geo_service.get_locations_needing_review)
    update_entity_location = staticmethod(geo_service.update_entity_location)
    remove_entity_location = staticmethod(geo_service.remove_entity_location)
    update_location = staticmethod(graph_edit_service.update_location)
    remove_location = staticmethod(graph_edit_service.remove_location)
    get_all_nodes = staticmethod(geo_service.get_all_nodes)
    update_entity_location_full = staticmethod(geo_service.update_entity_location_full)
    create_location_node = staticmethod(geo_service.create_location_node)
    ensure_located_at_relationship = staticmethod(geo_service.ensure_located_at_relationship)

    # ── Timeline ───────────────────────────────────────────────────────
    get_timeline_events = staticmethod(timeline_service.get_timeline_events)
    get_timeline_page = staticmethod(timeline_service.get_timeline_page)
    get_timeline_events_by_keys = staticmethod(timeline_service.get_timeline_events_by_keys)

    # ── Cellebrite analytics ───────────────────────────────────────────
    get_cellebrite_reports = staticmethod(cellebrite_service.get_cellebrite_reports)
    find_existing_phone_report = staticmethod(cellebrite_service.find_existing_phone_report)
    delete_phone_report = staticmethod(cellebrite_service.delete_phone_report)
    update_phone_report_name_override = staticmethod(cellebrite_service.update_phone_report_name_override)
    get_cellebrite_cross_phone_graph = staticmethod(cellebrite_service.get_cellebrite_cross_phone_graph)
    get_cellebrite_timeline = staticmethod(cellebrite_service.get_cellebrite_timeline)
    get_cellebrite_communication_network = staticmethod(cellebrite_service.get_cellebrite_communication_network)
    get_cellebrite_comms_entities = staticmethod(cellebrite_service.get_cellebrite_comms_entities)
    get_cellebrite_comms_source_apps = staticmethod(cellebrite_service.get_cellebrite_comms_source_apps)
    get_cellebrite_comms_threads = staticmethod(cellebrite_service.get_cellebrite_comms_threads)
    get_cellebrite_thread_detail = staticmethod(cellebrite_service.get_cellebrite_thread_detail)
    get_cellebrite_comms_between = staticmethod(cellebrite_service.get_cellebrite_comms_between)
    get_cellebrite_comms_envelope = staticmethod(cellebrite_service.get_cellebrite_comms_envelope)
    search_cellebrite_comms_messages = staticmethod(cellebrite_service.search_cellebrite_comms_messages)
    get_cellebrite_events = staticmethod(cellebrite_service.get_cellebrite_events)
    get_cellebrite_event_types = staticmethod(cellebrite_service.get_cellebrite_event_types)
    get_cellebrite_location_suggestion_values = staticmethod(cellebrite_service.get_cellebrite_location_suggestion_values)
    get_cellebrite_location_tiles = staticmethod(cellebrite_service.get_cellebrite_location_tiles)
    get_cellebrite_locations_in_tile = staticmethod(cellebrite_service.get_cellebrite_locations_in_tile)
    get_cellebrite_location_visitors = staticmethod(cellebrite_service.get_cellebrite_location_visitors)
    get_cellebrite_event_tracks = staticmethod(cellebrite_service.get_cellebrite_event_tracks)
    get_cellebrite_event_detail = staticmethod(cellebrite_service.get_cellebrite_event_detail)
    get_event_related = staticmethod(cellebrite_service.get_event_related)
    get_overview_contacts = staticmethod(cellebrite_service.get_overview_contacts)
    get_unified_contacts = staticmethod(cellebrite_service.get_unified_contacts)
    get_overview_calls = staticmethod(cellebrite_service.get_overview_calls)
    get_overview_messages = staticmethod(cellebrite_service.get_overview_messages)
    get_overview_locations = staticmethod(cellebrite_service.get_overview_locations)
    get_overview_emails = staticmethod(cellebrite_service.get_overview_emails)
    get_overview_contact_detail = staticmethod(cellebrite_service.get_overview_contact_detail)
    get_contact_comms_feed = staticmethod(cellebrite_service.get_contact_comms_feed)
    resolve_cellebrite_file_parents = staticmethod(cellebrite_service.resolve_file_parents)


neo4j_service = Neo4jServiceFacade()
