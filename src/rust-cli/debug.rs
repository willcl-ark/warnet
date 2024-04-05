use serde_json::{json, Value};
use std::path::PathBuf;

use clap::Subcommand;

use crate::rpc_call::make_rpc_call;

#[derive(Subcommand, Debug)]
pub enum DebugCommand {
    /// Generate the docker-compose file for a given graph_file
    GenerateCompose {
        /// Path to graph file to generate from
        graph_file_path: PathBuf,
    },
}

pub fn handle_debug_command(command: &DebugCommand, mut rpc_params: Value) -> anyhow::Result<()> {
    match command {
        DebugCommand::GenerateCompose { graph_file_path } => {
            rpc_params["graph_file"] = json!(graph_file_path.to_str());
            let data = make_rpc_call("generate_compose", &rpc_params);
            println!("Docker-compose file generated: {:?}", data);
        }
    }
    Ok(())
}
