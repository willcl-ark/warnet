use rand::seq::SliceRandom;
use rand::thread_rng;
use std::borrow::Cow;
use std::fs::File;
use std::io::Cursor;
use std::path::{Path, PathBuf};

use crate::graphml::GraphML;
use crate::util::{dump_bitcoin_conf, parse_bitcoin_conf};
use anyhow::Context;
use clap::Subcommand;
use petgraph::graph::{DiGraph, NodeIndex};
use xmltree::{Element, EmitterConfig, XMLNode};

#[derive(Subcommand, Debug)]
pub enum GraphCommand {
    /// Create a cycle graph with 7 extra random outbounds per node.
    Create {
        /// Number of nodes in the graph
        number: usize,
        /// Write graph to this file path
        #[arg(short, long)]
        outfile: Option<PathBuf>,
        /// Bitcoin Core version to set on nodes
        #[arg(short, long)]
        version: Option<String>,
        /// config values to add to bitcoin.conf
        #[arg(short, long)]
        bitcoin_conf: Option<PathBuf>,
    },
    /// (broken) Validate a *.graphml file against the graph schema
    Validate {
        /// Path to graph file
        graph: PathBuf,
    },
}

fn create_graph(number: usize) -> anyhow::Result<DiGraph<(), ()>> {
    // Create initial cycle graph
    let mut graph = DiGraph::new();
    let mut last_node: Option<NodeIndex> = None;
    let mut first_node: Option<NodeIndex> = None;

    for _ in 0..number {
        let new_node = graph.add_node(());
        if let Some(ln) = last_node {
            graph.add_edge(ln, new_node, ()); // Add an edge from the last node to the new one
        } else {
            first_node = Some(new_node);
        }
        last_node = Some(new_node);
    }

    if number > 0 {
        if let (Some(first), Some(last)) = (first_node, last_node) {
            graph.add_edge(last, first, ()); // Connect the last node to the first to complete the cycle
        }
    }

    // Add more outbound connections to each node
    for node in graph.node_indices() {
        let mut candidates = Vec::new();
        for potential_target in graph.node_indices() {
            if node != potential_target && !graph.contains_edge(node, potential_target) {
                candidates.push(potential_target);
            }
        }
        // Add 7 extra outbounds
        for _ in 0..7 {
            if let Some(&random_target) = candidates.choose(&mut thread_rng()) {
                graph.add_edge(node, random_target, ());
                // Remove the selected target from candidates to avoid trying to add it again
                candidates.retain(|&x| x != random_target);
            }
        }
    }
    Ok(graph)
}

fn handle_bitcoin_conf(bitcoin_conf: Option<&Path>) -> String {
    let mut conf_contents: String = String::new();
    if bitcoin_conf.is_some() {
        let conf = parse_bitcoin_conf(bitcoin_conf);
        // Iterate over sections and their properties
        for (section, prop) in &conf {
            println!("[{:?}]", section);
            for (key, value) in prop.iter() {
                println!("{}={}", key, value);
            }
        }
        conf_contents += &dump_bitcoin_conf(&conf);
    };
    conf_contents
}

fn convert_to_graphml(graph: &petgraph::graph::DiGraph<(), ()>) -> anyhow::Result<Vec<u8>> {
    let graphml = petgraph_graphml::GraphMl::new(graph).pretty_print(true);
    let mut buf = Vec::new();
    graphml
        .to_writer(&mut buf)
        .expect("Failed to write GraphML data");
    Ok(buf)
}

fn add_custom_attributes(
    graphml_buf: Vec<u8>,
    version_str: &str,
    bitcoin_conf: &str,
) -> xmltree::Element {
    let cursor = Cursor::new(graphml_buf);
    let mut graphml_element = Element::parse(cursor).unwrap();

    let keys = vec![
        ("version", "string"),
        ("bitcoin_config", "string"),
        ("tc_netem", "string"),
        ("build_args", "string"),
        ("exporter", "boolean"),
        ("collect_logs", "boolean"),
        ("image", "string"),
    ];
    for (attr_name, attr_type) in keys {
        let mut key_element = Element::new("key");
        key_element
            .attributes
            .insert("attr.name".to_string(), attr_name.to_string());
        key_element
            .attributes
            .insert("attr.type".to_string(), attr_type.to_string());
        key_element
            .attributes
            .insert("for".to_string(), "node".to_string());
        key_element
            .attributes
            .insert("id".to_string(), attr_name.to_string());

        graphml_element.children.push(XMLNode::Element(key_element));
    }
    // Find the <graph> element first
    if let Some(XMLNode::Element(graph_el)) = graphml_element
        .children
        .iter_mut()
        .find(|e| matches!(e, XMLNode::Element(el) if el.name == "graph"))
    {
        // Iterate over the children of the <graph> element to find <node> elements
        for node in graph_el.children.iter_mut() {
            if let XMLNode::Element(ref mut el) = node {
                if el.name == "node" {
                    let data_elements = vec![
                        ("version", version_str),
                        ("bitcoin_config", bitcoin_conf),
                        ("tc_netem", ""),
                        ("build_args", ""),
                        ("exporter", "false"),
                        ("collect_logs", "false"),
                        ("image", ""),
                    ];
                    for (key, value) in data_elements {
                        let mut data_element = Element::new("data");
                        data_element
                            .attributes
                            .insert("key".to_string(), key.to_string());
                        data_element.children.push(XMLNode::Text(value.to_string()));
                        el.children.push(XMLNode::Element(data_element));
                    }
                }
            }
        }
    }
    graphml_element
}

fn validate_schema(graph: &PathBuf) -> anyhow::Result<()> {
    // Our graphml files should include a "key" section describing kinds of values available in each
    // node. The parsing logic in GraphML does similar validation work as the existing python
    // validation approach.
    let _ = GraphML::from_file(graph).context("Could not load and parse graphml file")?;

    Ok(())
}

fn handle_create_command(
    number: &usize,
    outfile: &Option<PathBuf>,
    version: &Option<String>,
    bitcoin_conf: &Option<PathBuf>,
) -> anyhow::Result<()> {
    let version_str: &str = version.as_deref().unwrap_or("26.0");

    // Create empty graph
    let graph: DiGraph<(), ()> = create_graph(*number).context("creating graph")?;

    // Parse any custom bitcoin conf
    let bitcoin_conf: String = handle_bitcoin_conf(bitcoin_conf.as_deref());

    // Dump graph to graphml format
    let graphml_buf: Vec<u8> = convert_to_graphml(&graph).context("Convert to graphml")?;

    // Configure graphml output settings
    let graphml_config = EmitterConfig {
        write_document_declaration: true,
        perform_indent: true,
        indent_string: Cow::Borrowed("    "),
        line_separator: Cow::Borrowed("\n"),
        ..Default::default() // Keep other defaults
    };

    // Add custom elements to graph
    let modified_graphml: xmltree::Element =
        add_custom_attributes(graphml_buf, version_str, bitcoin_conf.as_str());

    // Write either to outfile or stdout
    match outfile {
        Some(path) => {
            let file = File::create(path).context("Writing final graphml file")?;
            modified_graphml.write_with_config(file, graphml_config)?;
        }
        None => {
            let stdout = std::io::stdout();
            let handle = stdout.lock();
            modified_graphml.write_with_config(handle, graphml_config)?;
        }
    }
    Ok(())
}

pub async fn handle_graph_command(command: &GraphCommand) -> anyhow::Result<()> {
    match command {
        GraphCommand::Create {
            number,
            outfile,
            version,
            bitcoin_conf,
        } => handle_create_command(number, outfile, version, bitcoin_conf)
            .context("Create a graph")?,

        GraphCommand::Validate { graph } => {
            let _ = validate_schema(graph).context("Validating graph schema");
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::{io::Write, str::FromStr};

    use super::*;

    static GRAPHML_FILE: &str = r#"<?xml version='1.0' encoding='utf-8'?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
  <key id="image" for="node" attr.name="image" attr.type="string" />
  <key id="collect_logs" for="node" attr.name="collect_logs" attr.type="boolean" />
  <key id="exporter" for="node" attr.name="exporter" attr.type="boolean" />
  <key id="build_args" for="node" attr.name="build_args" attr.type="string" />
  <key id="tc_netem" for="node" attr.name="tc_netem" attr.type="string" />
  <key id="bitcoin_config" for="node" attr.name="bitcoin_config" attr.type="string" />
  <key id="version" for="node" attr.name="version" attr.type="string" />
  <graph edgedefault="directed">
    <node id="0">
      <data key="version">26.0</data>
      <data key="bitcoin_config" />
      <data key="tc_netem"></data>
      <data key="build_args" />
      <data key="exporter">False</data>
      <data key="collect_logs">False</data>
    </node>
    <node id="1">
      <data key="image">bitcoindevproject/bitcoin:26.0</data>
      <data key="bitcoin_config" />
      <data key="tc_netem" />
      <data key="build_args" />
      <data key="exporter">False</data>
      <data key="collect_logs">False</data>
    </node>
    <node id="2">
      <data key="version">26.0</data>
      <data key="bitcoin_config" />
      <data key="tc_netem" />
      <data key="build_args" />
      <data key="exporter">False</data>
      <data key="collect_logs">False</data>
    </node>
    <node id="3">
      <data key="version">26.0</data>
      <data key="bitcoin_config" />
      <data key="tc_netem" />
      <data key="build_args" />
      <data key="exporter">False</data>
      <data key="collect_logs">False</data>
    </node>
    <node id="4">
      <data key="version">26.0</data>
      <data key="bitcoin_config" />
      <data key="tc_netem" />
      <data key="build_args" />
      <data key="exporter">False</data>
      <data key="collect_logs">False</data>
    </node>
    <edge source="0" target="1" id="0" />
    <edge source="0" target="2" id="0" />
    <edge source="0" target="3" id="0" />
    <edge source="1" target="2" id="0" />
    <edge source="1" target="3" id="0" />
    <edge source="1" target="4" id="0" />
    <edge source="2" target="3" id="0" />
    <edge source="2" target="4" id="0" />
    <edge source="3" target="4" id="0" />
    <edge source="4" target="0" id="0" />
  </graph>
</graphml>
"#;

    #[test]
    fn validate_graphml() {
        let path = "temp_graphml_file_for_validate_graphml_test.xml";
        let mut file = std::fs::File::create(path).unwrap();
        file.write_all(GRAPHML_FILE.as_bytes()).unwrap();
        let schema_is_valid = match validate_schema(&PathBuf::from_str(path).unwrap()) {
            Ok(_) => true,
            Err(e) => {
                println!("{:?}", e);
                false
            }
        };
        assert!(schema_is_valid);
        std::fs::remove_file(path).unwrap();
    }
}
