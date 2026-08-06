use std::{io::{BufRead,BufReader},os::unix::net::{UnixListener,UnixStream},thread,time::Duration};
fn handle(s:UnixStream){let _=s.set_read_timeout(Some(Duration::from_secs(5)));let mut line=String::new();let _=BufReader::new(s).read_line(&mut line);}
fn main(){let p=std::env::args().nth(1).unwrap_or("/run/rill-xray-agent/native-runtime.sock".into());let _=std::fs::remove_file(&p);let l=UnixListener::bind(p).unwrap();for c in l.incoming(){if let Ok(s)=c{thread::spawn(move||handle(s));}}}
