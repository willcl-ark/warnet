use crate::rpc_call::make_rpc_call;
use anyhow::Context;
use serde_json::{json, Value};

use crate::util::pretty_print_value;

pub enum NodeType {
    LnCli,
    BitcoinCli,
}

pub fn handle_rpc_commands(
    node_type: NodeType,
    node_index: &u64,
    method: &String,
    rpc_params: &Option<Vec<String>>,
    mut params: Value,
) -> anyhow::Result<()> {
    params["node"] = json!(node_index);
    params["method"] = json!(method);
    if let Some(p) = rpc_params {
        params["params"] = json!(p);
    }
    let data = match node_type {
        NodeType::LnCli => make_rpc_call("tank_lncli", &params).context("make RPC call lncli")?,
        NodeType::BitcoinCli => {
            make_rpc_call("tank_bcli", &params).context("make RPC call bitcoin-cli")?
        }
    };
    pretty_print_value(&data).context("Pretty print the result")?;
    Ok(())
}

pub fn handle_debug_log_command(node: &u64, mut params: Value) -> anyhow::Result<()> {
    params["node"] = json!(node);
    let data = make_rpc_call("tank_debug_log", &params).context("make RPC call tank_debug_log")?;
    pretty_print_value(&data).context("pretty print result")?;
    Ok(())
}

pub fn handle_messages_command(
    node_a: &u64,
    node_b: &u64,
    mut params: Value,
) -> anyhow::Result<()> {
    params["node_a"] = json!(node_a);
    params["node_b"] = json!(node_b);
    let data =
        make_rpc_call("tank_messages", &params).context("Failed to make RPC call tank_messages")?;
    pretty_print_value(&data).context("pretty print result")?;
    Ok(())
}

pub fn handle_grep_logs_command(pattern: &String, mut params: Value) -> anyhow::Result<()> {
    params["pattern"] = json!(pattern);
    let data =
        make_rpc_call("logs_grep", &params).context("Failed to make RPC call tank_messages")?;
    pretty_print_value(&data).context("pretty print result")?;
    Ok(())
}

pub fn handle_stop_command(params: Value) -> anyhow::Result<()> {
    let data =
        make_rpc_call("server_stop", &params).context("Failed to make RPC call server_stop")?;
    pretty_print_value(&data).context("pretty print result")?;
    Ok(())
}
