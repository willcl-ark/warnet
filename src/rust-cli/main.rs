use clap::{Parser, Subcommand};
use debug::handle_debug_command;
use network::handle_network_command;
use serde_json::json;

mod debug;
mod general;
mod graph;
mod image;
mod network;
mod rpc_call;
mod scenarios;
mod util;
use crate::debug::DebugCommand;
use crate::general::*;
use crate::graph::{handle_graph_command, GraphCommand};
use crate::image::{handle_image_command, ImageCommand};
use crate::network::NetworkCommand;
use crate::scenarios::{handle_scenario_command, ScenarioCommand};

#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
struct Cli {
    #[arg(long)]
    /// The warnet network command corresponds to
    network: Option<String>,

    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand, Debug)]
enum Commands {
    /// Debug commands (deprecated)
    Debug {
        #[command(subcommand)]
        command: Option<DebugCommand>,
    },
    /// Fetch the Bitcoin Core debug log from a node
    DebugLog {
        /// Node index (integer)
        node: u64,
    },
    /// Graph commands
    Graph {
        #[command(subcommand)]
        command: Option<GraphCommand>,
    },
    /// Grep combined logs using regex
    GrepLogs {
        /// Pattern to search for (as regex)
        pattern: String,
    },
    /// Build a warnet-ready bitcoind docker image from a github branch
    Image {
        #[command(subcommand)]
        command: Option<ImageCommand>,
    },
    /// Call "lncli ..." on a node
    LnCli {
        /// Node index (integer)
        node: u64,
        /// lncli method
        method: String,
        /// Optional arguments to method
        params: Option<Vec<String>>,
    },
    /// Fetch bitcoin P2P messages sent between two nodes
    Messages {
        /// First node
        node_a: u64,
        /// Second node
        node_b: u64,
    },
    /// Network commands
    Network {
        #[command(subcommand)]
        command: Option<NetworkCommand>,
    },
    /// Call "bitcoin-cli ..." on a node
    Rpc {
        /// Node index (integer)
        node: u64,
        /// bitcoin-cli method
        #[arg(allow_hyphen_values = true)]
        method: String,
        /// Optional arguments to method
        params: Option<Vec<String>>,
    },
    /// Scenario commands
    Scenarios {
        #[command(subcommand)]
        command: Option<ScenarioCommand>,
    },
    /// Stop warnet server
    Stop {},
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();

    let mut rpc_params = json!({});
    if let Some(network_value) = &cli.network {
        rpc_params["network"] = json!(network_value);
    }

    match &cli.command {
        Some(Commands::Debug { command }) => {
            if let Some(command) = command {
                handle_debug_command(command, rpc_params)?;
            }
        }
        Some(Commands::Graph { command }) => {
            if let Some(command) = command {
                handle_graph_command(command)?;
            }
        }
        Some(Commands::Network { command }) => {
            if let Some(command) = command {
                handle_network_command(command, rpc_params)?;
            }
        }
        Some(Commands::Scenarios { command }) => {
            if let Some(command) = command {
                handle_scenario_command(command, rpc_params)?;
            }
        }
        Some(Commands::Rpc {
            node,
            method,
            params,
        }) => {
            handle_rpc_commands(NodeType::BitcoinCli, node, method, params, rpc_params)?;
        }
        Some(Commands::LnCli {
            node,
            method,
            params,
        }) => {
            handle_rpc_commands(NodeType::LnCli, node, method, params, rpc_params)?;
        }
        Some(Commands::DebugLog { node }) => {
            handle_debug_log_command(node, rpc_params)?;
        }
        Some(Commands::Image { command }) => {
            if let Some(command) = command {
                handle_image_command(command)?;
            }
        }
        Some(Commands::Messages { node_a, node_b }) => {
            handle_messages_command(node_a, node_b, rpc_params)?;
        }
        Some(Commands::GrepLogs { pattern }) => {
            handle_grep_logs_command(pattern, rpc_params)?;
        }
        Some(Commands::Stop {}) => {
            handle_stop_command(rpc_params)?;
        }
        None => println!("No command provided"),
    }

    Ok(())
}
