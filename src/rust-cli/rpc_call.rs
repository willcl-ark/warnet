use anyhow::Context;
use jsonrpc::{simple_http::SimpleHttpTransport, Client};

use serde_json::{value::to_raw_value, Value};

pub fn make_rpc_call(request: &str, params: &Value) -> anyhow::Result<serde_json::Value> {
    let params = to_raw_value(&params)?;
    let url = "http://127.0.0.1:9276/api";
    let t = SimpleHttpTransport::builder().url(url)?.build();
    let client = Client::with_transport(t);
    let req = client.build_request(request, Some(&params));
    let response = client.send_request(req)?;
    response
        .result()
        .with_context(|| format!("RPC call failed: {}", request))
}
