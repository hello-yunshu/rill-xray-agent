use serde::{Deserialize,Serialize};
#[derive(Debug,Clone,Serialize,Deserialize)]#[serde(rename_all="camelCase")]pub struct Envelope{pub schema_version:u32,pub request_id:String,pub capability:String,pub method:String,pub body:serde_json::Value}
pub const METHODS:&[&str]=&["health","metrics","mode","config","register","rootResult","feedback","inspect","snapshot"];
