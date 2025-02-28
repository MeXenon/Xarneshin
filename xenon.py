#!/usr/bin/env python3
import sys
import logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
import json
import io
import datetime
import random
import secrets
import base64
import subprocess
import time
import os
import requests
from flask import (
    Flask, request, render_template, session, redirect, url_for,
    jsonify, flash, Response, stream_with_context
)
from assets.getinfo import getinfo_bp
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
##################### by MeXenon ###########################
###############################################################################
#                  LOAD DYNAMIC CONFIG FROM ports.json                       #
###############################################################################
import os

CONFIG_FILE = "/opt/Xenon.xray/ports.json"

def get_config():
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        return {
            "panel_port": data.get("panel_port", 8000),
            "flask_port": data.get("flask_port", 42689),
            "panel_use_https": data.get("panel_use_https", False),
            "use_https": data.get("use_https", False),
            "domain": data.get("domain", ""),
            "cert_file": data.get("cert_file", ""),
            "key_file": data.get("key_file", "")
        }

config = get_config()
PANEL_PORT = config["panel_port"]
FLASK_PORT = config["flask_port"]
PANEL_USE_HTTPS = config["panel_use_https"]
USE_HTTPS = config["use_https"]
DOMAIN = config["domain"]
CERT_FILE = config["cert_file"]
KEY_FILE = config["key_file"]

###############################################################################
#                           FLASK APP DEFINITION                              #
###############################################################################
app = Flask(__name__, template_folder="/opt/Xenon.xray/templates")
app.secret_key = secrets.token_bytes(32)
HOST = "0.0.0.0"
PORT = FLASK_PORT

###############################################################################
#                        GLOBAL REQUESTS SESSION                              #
###############################################################################
# mode rule
api_session = requests.Session()
API_BASE_URL = f"{'https' if PANEL_USE_HTTPS else 'http'}://127.0.0.1:{PANEL_PORT}/api"
# https handler
api_session.verify = not PANEL_USE_HTTPS

###############################################################################
#                             API BRIDGE FUNCTIONS                            #
###############################################################################
def get_token(username, password):
    url = f"{API_BASE_URL}/admins/token"
    data = {
        "username": username,
        "password": password,
        "grant_type": "password"
    }
    try:
        response = api_session.post(url, data=data)
        if response.status_code == 200:
            return response.json().get("access_token")
    except Exception as e:
        print(e)
    return None

def get_nodes(token):
    url = f"{API_BASE_URL}/nodes?page=1&size=100&descending=true&order_by=created_at"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = api_session.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(e)
    return None
#################### core v changer 
####################
@app.route("/get_xray_versions", methods=["GET"])
def get_xray_versions():
    """
    Fetch the latest 20 stable Xray versions using xrayc.sh -list 20
    Returns a JSON response with versions or an error message
    I thought maybe 20 Is enough but if you think You can't find your desire version...
    increase the number ...
    """
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    script_path = "/opt/Xenon.xray/assets/xrayc.sh"
    if not os.path.isfile(script_path) or not os.access(script_path, os.X_OK):
        logger.error(f"Script {script_path} not found or not executable")
        return jsonify({"error": "Version fetch script not available"}), 500

    try:
        result = subprocess.run(
            ['sudo', script_path, '-list', '20'],
            capture_output=True,
            text=True,
            check=True
        )
        versions = result.stdout.strip().split('\n')
        if not versions or versions[0].startswith('{"status": "error"'):
            error_json = json.loads(versions[0])
            return jsonify({"error": error_json["message"]}), 500
        return jsonify({"versions": versions})
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch versions: {e.stderr}")
        return jsonify({"error": f"Failed to fetch versions: {e.stderr}"}), 500
    except Exception as e:
        logger.error(f"Unexpected error fetching versions: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route("/change_core/<int:node_id>", methods=["POST"])
def change_core(node_id):
    logger.debug(f"Starting change_core for node_id: {node_id}")
    if "token" not in session:
        logger.warning("Unauthorized access attempt")
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "version" not in data or not isinstance(data["version"], str):
        logger.error(f"Invalid or missing version in request data: {data}")
        return jsonify({"error": "Version must be a non-empty string"}), 400

    selected_version = data["version"]
    token = session["token"]
    logger.debug(f"Selected version: {selected_version}")

    node_data = get_node(token, node_id)
    if not node_data or node_data.get("name") != "local":
        logger.error(f"Invalid node or not local: {node_data}")
        return jsonify({"error": "This operation is only allowed on the local node"}), 403

    script_path = "/opt/Xenon.xray/assets/xrayc.sh"
    logger.debug(f"Script path: {script_path}")

    if not os.path.isfile(script_path) or not os.access(script_path, os.X_OK):
        logger.error(f"Script not found or not executable at {script_path}")
        return Response(
            f"data: {{\"progress\": 100, \"message\": \"Error: Script not found or not executable at {script_path}\", \"error\": true}}\n\n",
            mimetype="text/event-stream"
        )

    import select

    def generate():
        args = ['sudo', 'stdbuf', '-oL', script_path, selected_version]
        logger.debug(f"Subprocess args: {args}")
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env={"PYTHONUNBUFFERED": "1", "PATH": os.environ["PATH"]}
        )
        logger.debug(f"Subprocess started with PID: {process.pid}")

        yield "data: {\"progress\": 0, \"message\": \"Initializing...\"}\n\n"

        while True:
            streams = [process.stdout, process.stderr]
            ready, _, _ = select.select(streams, [], [], 0.1)
            for s in ready:
                line = s.readline().strip()
                if line:
                    if s == process.stdout:
                        logger.debug(f"Realtime STDOUT: {line}")
                        try:
                            data = json.loads(line)
                            yield f"data: {json.dumps(data)}\n\n"
                        except json.JSONDecodeError:
                            logger.debug(f"Ignoring non-JSON stdout: {line}")
                    else:
                        logger.error(f"Realtime STDERR: {line}")
                        yield f"data: {json.dumps({'progress': 100, 'message': f'Error: {line}', 'error': True})}\n\n"
            if process.poll() is not None:
                break

        for s in [process.stdout, process.stderr]:
            remaining = s.read()
            for line in remaining.splitlines():
                line = line.strip()
                if line:
                    if s == process.stdout:
                        logger.debug(f"Final STDOUT: {line}")
                        try:
                            data = json.loads(line)
                            yield f"data: {json.dumps(data)}\n\n"
                        except json.JSONDecodeError:
                            logger.debug(f"Ignoring final non-JSON stdout: {line}")
                    else:
                        logger.error(f"Final STDERR: {line}")
                        yield f"data: {json.dumps({'progress': 100, 'message': f'Error: {line}', 'error': True})}\n\n"
        process.stdout.close()
        process.stderr.close()

    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"X-Accel-Buffering": "no"})

#################### end xray core changr
####################
####################### Restart core section
@app.route("/node/<int:node_id>/restart_cores", methods=["POST"])
def restart_cores(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "cores" not in data:
        return jsonify({"error": "No cores specified"}), 400

    cores = data["cores"]
    if not isinstance(cores, list) or 'xray' not in cores:
        return jsonify({"error": "Only 'xray' core restart is supported"}), 400

    token = session["token"]
    results = {}

    # Validate node and Xray presence
    node_data = get_node(token, node_id)
    if not node_data or "backends" not in node_data:
        return jsonify({"error": "Failed to fetch node details"}), 500
    if not any(backend["name"] == "xray" for backend in node_data["backends"]):
        results["xray"] = {"status": "error", "message": "Xray core not found in node"}
        return jsonify(results)

    # Restart Xray only
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch current Xray config
    try:
        response = api_session.get(url, headers=headers)
        if response.status_code != 200:
            results["xray"] = {"status": "error", "message": f"Failed to fetch config (status: {response.status_code})"}
            return jsonify(results)
    except requests.RequestException as e:
        results["xray"] = {"status": "error", "message": f"Fetch error: {str(e)}"}
        return jsonify(results)

    config_data = response.json()
    if "config" not in config_data:
        results["xray"] = {"status": "error", "message": "Config not found in response"}
        return jsonify(results)

    # Resubmit Xray config to restart
    try:
        put_response = api_session.put(
            url,
            headers=headers,
            json={"config": config_data["config"], "format": 1}
        )
        if put_response.status_code == 200:
            results["xray"] = {"status": "success"}
        else:
            results["xray"] = {"status": "error", "message": f"Failed to update config (status: {put_response.status_code})"}
    except requests.RequestException as e:
        results["xray"] = {"status": "error", "message": f"Update error: {str(e)}"}

    return jsonify(results)

@app.route("/restart_all_nodes_cores", methods=["POST"])
def restart_all_nodes_cores():
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    token = session["token"]
    nodes_data = get_nodes(token)
    if not nodes_data or "items" not in nodes_data:
        return jsonify({"error": "Failed to fetch nodes"}), 500

    results = {}
    for node in nodes_data["items"]:
        node_id = node["id"]
        node_results = {}
        # Only process Xray core
        if any(backend["name"] == "xray" for backend in node["backends"]):
            url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
            headers = {"Authorization": f"Bearer {token}"}
            try:
                response = api_session.get(url, headers=headers)
                if response.status_code != 200:
                    node_results["xray"] = {"status": "error", "message": f"Fetch failed (status: {response.status_code})"}
                else:
                    config_data = response.json()
                    if "config" not in config_data:
                        node_results["xray"] = {"status": "error", "message": "Config not found"}
                    else:
                        put_response = api_session.put(url, headers=headers, json={"config": config_data["config"], "format": 1})
                        if put_response.status_code == 200:
                            node_results["xray"] = {"status": "success"}
                        else:
                            node_results["xray"] = {"status": "error", "message": f"Update failed (status: {put_response.status_code})"}
            except requests.RequestException as e:
                node_results["xray"] = {"status": "error", "message": f"Error: {str(e)}"}
        else:
            node_results["xray"] = {"status": "skipped", "message": "Xray not present"}
        results[node_id] = node_results

    return jsonify(results)
####################
####################
def get_xray_config(token, node_id):
    """
    Fetch the node's Xray config JSON from the backend API
    """
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {"Authorization": f"Bearer {token}"}
    r = api_session.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return None

def update_xray_inbounds(token, node_id, new_inbounds):
    """
    Re-writes the 'inbounds' section in the Xray config JSON for the specified node.
    """
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    current = get_xray_config(token, node_id)
    if not current or "config" not in current:
        return False
    try:
        decoded = json.loads(current["config"])
    except:
        return False
    decoded["inbounds"] = new_inbounds
    updated_str = json.dumps(decoded, indent=2)
    body = {
        "config": updated_str,
        "format": 1
    }
    try:
        put_resp = api_session.put(url, headers=headers, data=json.dumps(body))
        return (put_resp.status_code == 200)
    except:
        return False

def update_xray_outbounds(token, node_id, new_outbounds):
    """
    Re-writes the 'outbounds' section in the Xray config JSON for the specified node.
    """
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    current = get_xray_config(token, node_id)
    if not current or "config" not in current:
        return False
    try:
        decoded = json.loads(current["config"])
    except:
        return False
    decoded["outbounds"] = new_outbounds
    updated_str = json.dumps(decoded, indent=2)
    body = {
        "config": updated_str,
        "format": 1
    }
    try:
        resp = api_session.put(url, headers=headers, data=json.dumps(body))
        return (resp.status_code == 200)
    except:
        return False

def get_node(token, node_id):
    """
    Retrieve a single node's details from the API.
    Endpoint typically: /nodes/<node_id>
    """
    url = f"{API_BASE_URL}/nodes/{node_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = api_session.get(url, headers=headers)
    if r.status_code == 200:
        return r.json()
    return None

## ss paswd creation:
@app.route("/generate_ss_password", methods=["POST"])
def generate_ss_password():
    """
    Generate a reliable Shadowsocks password based on the provided encryption method.
    Expected JSON payload: { "method": "<encryption method>" }

    For Shadowsocks 2022 methods:
      - "2022-blake3-aes-128-gcm" requires a 16-byte key.
      - "2022-blake3-aes-256-gcm" and "2022-blake3-chacha20-poly1305" require a 32-byte key.
    For other encryption methods:
      - aes-256-gcm, aes-128-gcm,
      - chacha20-poly1305/chacha20-ietf-poly1305,
      - xchacha20-poly1305/xchacha20-ietf-poly1305,
    a random 16-character alphanumeric password is generated.
    """
    data = request.get_json()
    if not data or "method" not in data:
        return jsonify({"error": "Encryption method not provided."}), 400

    method = data["method"].strip()
    
    # For 2022 methods generate a key with a specific byte length
    if method == "2022-blake3-aes-128-gcm":
        key_length = 16
    elif method in ["2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305"]:
        key_length = 32
    elif method in [
        "aes-256-gcm", "aes-128-gcm",
        "chacha20-poly1305", "chacha20-ietf-poly1305",
        "xchacha20-poly1305", "xchacha20-ietf-poly1305"
    ]:
        import string
        length = 16  
        generated = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))
        return jsonify({"password": generated})
    else:
        import string
        length = 16
        generated = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))
        return jsonify({"password": generated})

    key_bytes = secrets.token_bytes(key_length)
    password = base64.urlsafe_b64encode(key_bytes).rstrip(b'=').decode('utf-8')
    return jsonify({"password": password})

#############################
# db to raw :) :
@app.route("/node/<int:node_id>/dbtoraw")
def dbtoraw_page(node_id):
    """
    Serve the dbtoraw.html template, passing node_id so the child page
    knows where to POST the new inbounds.
    """
    if "token" not in session:
        return redirect("/")
    return render_template("dbtoraw.html", node_id=node_id)

@app.route("/node/<int:node_id>/save_inbounds", methods=["POST"])
def save_inbounds_bulk(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    # Get existing config
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        return jsonify({"error": "Cannot retrieve config for update"}), 400

    try:
        raw_json = json.loads(config_data["config"])
    except:
        return jsonify({"error": "Config JSON parse error"}), 400

    inbounds = raw_json.get("inbounds", [])

    # Expecting JSON array of inbound objects
    new_inbounds = request.get_json()
    if not isinstance(new_inbounds, list):
        return jsonify({"error": "Payload must be a list of inbound objects"}), 400

    # For each inbound, either replace if tag already exists, or append
    for inbound_obj in new_inbounds:
        tag = inbound_obj.get("tag")
        if not tag:
            continue  # skip invalid inbound
        replaced = False
        # Check if inbound with same tag exists
        for idx, ib in enumerate(inbounds):
            if ib.get("tag") == tag:
                inbounds[idx] = inbound_obj
                replaced = True
                break
        if not replaced:
            inbounds.append(inbound_obj)

    # Update the config in Xray
    success = update_xray_inbounds(session["token"], node_id, inbounds)
    if success:
        return jsonify({"success": True, "message": "Inbounds saved successfully."})
    else:
        return jsonify({"error": "Failed to update inbounds on server."}), 500

#############################
### lez go for balancer manager :)
# ==================== BALANCER ENDPOINTS ====================

@app.route("/node/<int:node_id>/balancers")
def view_balancers(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve Xray config.")
        return redirect(url_for("show_nodes", node_id=node_id))

    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        flash("Config parse error.")
        return redirect(url_for("show_nodes", node_id=node_id))

    # Get current balancers from the routing section
    routing = config.get("routing", {})
    balancers = routing.get("balancers", [])

    # Gather outbound tags for selection
    outbound_tags = []
    for outbound in config.get("outbounds", []):
        tag = outbound.get("tag")
        if tag and tag not in outbound_tags:
            outbound_tags.append(tag)

    # Render the Balancer Editor page
    return render_template(
        "balancers.html",
        node_id=node_id,
        balancers=json.dumps(balancers),
        outbound_tags=json.dumps(outbound_tags)
    )

@app.route("/node/<int:node_id>/save_balancers", methods=["POST"])
def save_balancers(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON provided"}), 400

    new_balancers = data.get("balancers")
    if new_balancers is None:
        return jsonify({"error": "No balancers provided"}), 400

    # Fetch the current config from the node
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        return jsonify({"error": "Config not found"}), 400

    # Parse the existing config
    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        return jsonify({"error": "Config parse error", "message": str(e)}), 400

    # Ensure the routing block exists
    if "routing" not in config:
        config["routing"] = {}

    config["routing"]["balancers"] = new_balancers

    if "observatory" in data:
        config["observatory"] = data["observatory"]
    else:
        config.pop("observatory", None)

    if "burstObservatory" in data:
        config["burstObservatory"] = data["burstObservatory"]
    else:
        config.pop("burstObservatory", None)

    updated_str = json.dumps(config, indent=2)
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {session['token']}",
        "Content-Type": "application/json"
    }
    body = {
        "config": updated_str,
        "format": 1
    }

    try:
        put_resp = api_session.put(url, headers=headers, data=json.dumps(body))
        if put_resp.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Update failed", "status": put_resp.status_code}), 400
    except Exception as e:
        return jsonify({"error": "Exception during update", "message": str(e)}), 500

###############################################################################
#                   dns manager :)                             #
###############################################################################
# --- DNS Manager Section ---

def filter_empty(obj):
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if v not in ["", None, []]}
    elif isinstance(obj, list):
        return [filter_empty(item) if isinstance(item, dict) else item for item in obj]
    return obj

def update_xray_dns(token, node_id, new_dns):
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    current = get_xray_config(token, node_id)
    if not current or "config" not in current:
        return False
    try:
        decoded = json.loads(current["config"])
    except Exception as e:
        print("Error parsing existing config:", e)
        return False
    decoded["dns"] = new_dns
    updated_str = json.dumps(decoded, indent=2)
    body = {"config": updated_str, "format": 1}
    try:
        put_resp = api_session.put(url, headers=headers, data=json.dumps(body))
        return (put_resp.status_code == 200)
    except Exception as e:
        print("Error updating DNS config:", e)
        return False

@app.route("/api/node/<int:node_id>/dns", methods=["GET"])
def api_get_dns(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    config_data = get_xray_config(session["token"], node_id)
    dns_config = {}
    try:
        config = json.loads(config_data["config"])
        dns_config = config.get("dns", {})
    except Exception as e:
        print("Error loading DNS config:", e)
        dns_config = {}
    # Set defaults
    dns_config.setdefault("hosts", {})
    dns_config.setdefault("servers", [])
    dns_config.setdefault("clientIp", "")
    dns_config.setdefault("queryStrategy", "UseIP")
    dns_config.setdefault("disableCache", False)
    dns_config.setdefault("disableFallback", False)
    dns_config.setdefault("disableFallbackIfMatch", False)
    dns_config.setdefault("tag", "")
    return jsonify(dns_config)

@app.route("/api/node/<int:node_id>/dns", methods=["POST"])
def api_save_dns(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    new_dns = {}
    client_ip = data.get("globalClientIp", "").strip()
    if client_ip:
        new_dns["clientIp"] = client_ip
    qs = data.get("globalQueryStrategy", "UseIP").strip()
    if qs:
        new_dns["queryStrategy"] = qs
    new_dns["disableCache"] = bool(data.get("globalDisableCache", False))
    new_dns["disableFallback"] = bool(data.get("globalDisableFallback", False))
    new_dns["disableFallbackIfMatch"] = bool(data.get("globalDisableFallbackIfMatch", False))
    dns_tag = data.get("globalDnsTag", "").strip()
    if dns_tag:
        new_dns["tag"] = dns_tag

    # Hosts block (if needed)
    new_dns["hosts"] = data.get("hosts", {})

    # Process DNS servers array
    servers = data.get("servers", [])
    new_dns["servers"] = filter_empty(servers)
    new_dns = filter_empty(new_dns)

    success = update_xray_dns(session["token"], node_id, new_dns)
    if success:
        return jsonify({"success": True, "message": "DNS configuration updated successfully."})
    else:
        return jsonify({"error": "Failed to update DNS configuration."}), 500

@app.route("/node/<int:node_id>/dns")
def dns_settings(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    dns_config = {}
    try:
        config = json.loads(config_data["config"])
        dns_config = config.get("dns", {})
    except Exception as e:
        print("Error loading DNS config:", e)
        dns_config = {}
    return render_template("dns.html", node_id=node_id, dns_config=dns_config)

###############################################################################
#                   NEW ENDPOINT – GENERATE WARP                               #
###############################################################################
@app.route("/generate_warp", methods=["GET", "POST"])
def generate_warp():
    """
    Runs the warp.py script (located at /opt/Xenon.xray/assets/warp.py)
    and returns its JSON output.
    """
    try:
        output = subprocess.check_output(
            ["python3", "/opt/Xenon.xray/assets/warp.py"],
            stderr=subprocess.STDOUT
        )
        data = json.loads(output.decode("utf-8"))
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

###############################################################################
#                            ROUTES & LOGIC                                   #
###############################################################################
@app.route("/")
def root_index():
    if "token" in session:
        return redirect(url_for("show_nodes"))
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    token = get_token(username, password)
    if token:
        session["token"] = token
        session["username"] = username
        session["password"] = password
        return redirect(url_for("show_nodes"))
    else:
        flash("Invalid credentials or cannot connect to API.")
        return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/nodes")
def show_nodes():
    if "token" not in session:
        return redirect("/")
    nodes = get_nodes(session["token"])
    if not nodes:
        flash("Failed to fetch nodes.")
        return redirect("/")
    return render_template("nodes.html", nodes=nodes)

###############################################################################
#                      NODE OVERVIEW (FUTURISTIC)                             #
###############################################################################
@app.route("/node/<int:node_id>/overview")
def overview(node_id):
    if "token" not in session:
        return redirect("/")
    node_data = get_node(session["token"], node_id)
    if not node_data:
        flash("Failed to retrieve node details.")
        return redirect(url_for("show_nodes"))

    node_status = node_data.get("status", "unknown")
    xray_version = "unknown"
    backends = node_data.get("backends", [])
    for backend in backends:
        if backend.get("name") == "xray":
            xray_version = backend.get("version", "unknown")
            break

    stats = {
        "status": node_status,
        "xray_version": xray_version
    }
    return render_template("overview.html", node_id=node_id, stats=stats)

###############################################################################
#                              INBOUND ROUTES                                 #
###############################################################################
@app.route("/node/<int:node_id>/inbounds")
def view_inbounds(node_id):
    """
    Shows the Xray inbounds for the selected node.
    """
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve Xray config.")
        return redirect(url_for("show_nodes"))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Cannot parse Xray config.")
        return redirect(url_for("show_nodes"))

    inbounds = raw_json.get("inbounds", [])
    return render_template("inbounds.html", node_id=node_id, inbounds=inbounds)

@app.route("/node/<int:node_id>/add_inbound")
def add_inbound(node_id):
    if "token" not in session:
        return redirect("/")
    inbound_data = {}
    inbound_data_json = json.dumps({})
    default_port = random.randint(10000, 65535)
    protocols = ["vmess", "vless", "trojan", "shadowsocks"]
    security_options = ["none", "tls", "reality"]
    ss_methods = [
        "2022-blake3-aes-128-gcm",
        "2022-blake3-aes-256-gcm",
        "2022-blake3-chacha20-poly1305",
        "aes-256-gcm",
        "aes-128-gcm",
        "chacha20-poly1305",
        "chacha20-ietf-poly1305",
        "xchacha20-poly1305",
        "xchacha20-ietf-poly1305",
        "none"
    ]
    stream_transmissions = {
        "vmess": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "vless": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "trojan": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "shadowsocks": ["tcp", "udp", "tcp,udp", "raw", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"]
    }

    return render_template(
        "inbound_form.html",
        page_title="Add Inbound",
        formActionUrl=url_for("save_inbound", node_id=node_id),
        inbound_data=inbound_data,
        inbound_data_json=inbound_data_json,
        default_port=default_port,
        protocols=protocols,
        security_options=security_options,
        ss_methods=ss_methods,
        stream_transmissions=json.dumps(stream_transmissions),
        node_id=node_id,
        edit_mode=False
    )

@app.route("/node/<int:node_id>/edit_inbound/<path:inbound_tag>")
def edit_inbound(node_id, inbound_tag):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve config.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Invalid config JSON.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    inbounds = raw_json.get("inbounds", [])
    inbound_data = None
    for ib in inbounds:
        if ib.get("tag") == inbound_tag:
            inbound_data = ib
            break
    if not inbound_data:
        flash("Inbound not found by tag.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    inbound_data_json = json.dumps(inbound_data, indent=2)
    default_port = inbound_data.get("port", random.randint(10000, 65535))
    protocols = ["vmess", "vless", "trojan", "shadowsocks"]
    security_options = ["none", "tls", "reality"]
    ss_methods = [
        "2022-blake3-aes-128-gcm",
        "2022-blake3-aes-256-gcm",
        "2022-blake3-chacha20-poly1305",
        "aes-256-gcm",
        "aes-128-gcm",
        "chacha20-poly1305",
        "chacha20-ietf-poly1305",
        "xchacha20-poly1305",
        "xchacha20-ietf-poly1305",
        "none"
    ]
    stream_transmissions = {
        "vmess": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "vless": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "trojan": ["raw", "tcp", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"],
        "shadowsocks": ["tcp", "udp", "tcp,udp", "raw", "mKCP", "ws", "grpc", "httpupgrade", "xhttp"]
    }

    return render_template(
        "inbound_form.html",
        page_title=f"Edit Inbound (tag: {inbound_tag})",
        formActionUrl=url_for("save_inbound", node_id=node_id),
        inbound_data=inbound_data,
        inbound_data_json=inbound_data_json,
        default_port=default_port,
        protocols=protocols,
        security_options=security_options,
        ss_methods=ss_methods,
        stream_transmissions=json.dumps(stream_transmissions),
        node_id=node_id,
        edit_mode=True
    )

@app.route("/node/<int:node_id>/save_inbound/", methods=["POST"])
def save_inbound(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Cannot retrieve config for update.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Config JSON parse error.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    inbounds = raw_json.get("inbounds", [])

    new_inbound = {}
    new_inbound["tag"] = request.form.get("remark", "")
    new_inbound["listen"] = request.form.get("listen", "0.0.0.0")
    try:
        new_inbound["port"] = int(request.form.get("port", "0"))
    except ValueError:
        new_inbound["port"] = 0

    protocol = request.form.get("protocol", "")
    new_inbound["protocol"] = protocol

    # Default settings
    new_inbound["settings"] = {"clients": [], "decryption": "none"}
    if protocol == "shadowsocks":
        new_inbound["settings"] = {
            "password": request.form.get("ss_password", ""),
            "method": request.form.get("ss_method", ""),
            "email": request.form.get("ss_email", ""),
            "network": request.form.get("ss_network", "tcp,udp")
        }

    sec = request.form.get("security", "none")
    net = request.form.get("transmission", "tcp")
    stream = {"network": net, "security": sec}

    # TCP or RAW
    if net in ["raw", "tcp"]:
        tcp_settings = {
            "acceptProxyProtocol": (request.form.get("accept_proxy") == "on")
        }
        header_type = request.form.get("header_type", "none")
        if header_type == "http":
            http_request = {
                "version": request.form.get("http_request_version", "1.1"),
                "method": request.form.get("http_request_method", "GET"),
                "path": [p.strip() for p in request.form.get("http_request_paths", "/").split(",") if p.strip()],
                "headers": {}
            }
            req_names = request.form.getlist("http_request_header_name[]")
            req_values = request.form.getlist("http_request_header_value[]")
            for (n, v) in zip(req_names, req_values):
                if n.strip():
                    http_request["headers"][n.strip()] = [x.strip() for x in v.split(",") if x.strip()]
            http_response = {
                "version": request.form.get("http_response_version", "1.1"),
                "status": request.form.get("http_response_status", "200"),
                "reason": request.form.get("http_response_reason", "OK"),
                "headers": {}
            }
            resp_names = request.form.getlist("http_response_header_name[]")
            resp_values = request.form.getlist("http_response_header_value[]")
            for (n, v) in zip(resp_names, resp_values):
                if n.strip():
                    http_response["headers"][n.strip()] = [x.strip() for x in v.split(",") if x.strip()]
            tcp_settings["header"] = {
                "type": "http",
                "request": http_request,
                "response": http_response
            }
        else:
            tcp_settings["header"] = {"type": "none"}
        stream["tcpSettings"] = tcp_settings

    # mKCP
    if net == "mKCP":
        kcp_settings = {
            "mtu": int(request.form.get("kcp_mtu", "1350")),
            "tti": int(request.form.get("kcp_tti", "50")),
            "uplinkCapacity": int(request.form.get("kcp_uplink", "5")),
            "downlinkCapacity": int(request.form.get("kcp_downlink", "20")),
            "congestion": (request.form.get("kcp_congestion") == "on"),
            "readBufferSize": int(request.form.get("kcp_read_buffer", "2")),
            "writeBufferSize": int(request.form.get("kcp_write_buffer", "2")),
            "header": {"type": request.form.get("kcp_header", "none")}
        }
        seed = request.form.get("kcp_seed", "")
        if seed:
            kcp_settings["seed"] = seed
        stream["kcpSettings"] = kcp_settings

    # WS
    if net == "ws":
        stream["wsSettings"] = {
            "path": request.form.get("ws_path", "/"),
            "host": request.form.get("ws_host", "")
        }

    # gRPC
    if net == "grpc":
        stream["grpcSettings"] = {
            "serviceName": request.form.get("grpc_service", ""),
            "multiMode": (request.form.get("grpc_multiMode") == "on"),
            "idle_timeout": int(request.form.get("grpc_idle_timeout", "60")),
            "health_check_timeout": int(request.form.get("grpc_health_check_timeout", "20")),
            "permit_without_stream": (request.form.get("grpc_permit_without_stream") == "on"),
            "initial_windows_size": int(request.form.get("grpc_initial_windows_size", "0"))
        }

    # HTTP Upgrade
    if net == "httpupgrade":
        stream["httpupgradeSettings"] = {
            "path": request.form.get("httpupgrade_path", "/"),
            "host": request.form.get("httpupgrade_host", "")
        }

    # xHTTP
    if net == "xhttp":
        try:
            extra = json.loads(request.form.get("xhttp_extra", "{}"))
        except:
            extra = {}
        stream["xhttpSettings"] = {
            "path": request.form.get("xhttp_path", "/"),
            "host": request.form.get("xhttp_host", ""),
            "mode": request.form.get("xhttp_mode", "auto"),
            "extra": extra
        }

    # TLS
    if sec == "tls":
        tls_conf = {}
        tls_conf["serverName"] = request.form.get("tls_serverName", "xray.com")
        tls_conf["rejectUnknownSni"] = (request.form.get("reject_unknown_sni") == "on")
        tls_conf["allowInsecure"] = (request.form.get("allow_insecure") == "on")
        tls_conf["disableSystemRoot"] = (request.form.get("disable_system_root") == "on")
        tls_conf["enableSessionResumption"] = (request.form.get("enable_session_resumption") == "on")
        alpn_str = request.form.get("alpn", "h2,http/1.1")
        tls_conf["alpn"] = [x.strip() for x in alpn_str.split(",") if x.strip()]
        tls_conf["minVersion"] = request.form.get("min_version", "1.2")
        tls_conf["maxVersion"] = request.form.get("max_version", "1.3")
        tls_conf["cipherSuites"] = request.form.get("cipher_suites", "auto")
        tls_conf["fingerprint"] = request.form.get("tls_fingerprint", "chrome")
        pinned = request.form.get("pinned_cert_sha256", "")
        tls_conf["pinnedPeerCertificateChainSha256"] = [s.strip() for s in pinned.split(",") if s.strip()]
        tls_conf["masterKeyLog"] = request.form.get("master_key_log", "")
        cMode = request.form.get("cert_mode", "file")
        if cMode == "file":
            tls_conf["certificateFile"] = request.form.get("cert_file_path", "")
            tls_conf["keyFile"] = request.form.get("key_file_path", "")
        else:
            tls_conf["certificate"] = request.form.get("cert_content", "")
            tls_conf["key"] = request.form.get("key_content", "")
        stream["tlsSettings"] = tls_conf
    elif sec == "reality":
        reality_conf = {}
        reality_conf["dest"] = request.form.get("reality_dest", "example.com:443")
        try:
            reality_conf["xver"] = int(request.form.get("reality_xver", "0"))
        except:
            reality_conf["xver"] = 0
        reality_conf["serverNames"] = [
            s.strip() for s in request.form.get("reality_serverNames", "example.com").split(",") if s.strip()
        ]
        reality_conf["privateKey"] = request.form.get("reality_privateKey", "")
        reality_conf["publicKey"] = request.form.get("reality_publicKey", "")
        reality_conf["minClientVer"] = request.form.get("reality_minClientVer", "")
        reality_conf["maxClientVer"] = request.form.get("reality_maxClientVer", "")
        try:
            reality_conf["maxTimeDiff"] = int(request.form.get("reality_maxTimeDiff", "0"))
        except:
            reality_conf["maxTimeDiff"] = 0
        reality_conf["shortIds"] = [
            s.strip() for s in request.form.get("reality_shortIds", "").split(",") if s.strip()
        ]
        reality_conf["fingerprint"] = request.form.get("reality_fingerprint", "chrome")
        reality_conf["serverName"] = request.form.get("reality_serverName", "")
        reality_conf["spiderX"] = request.form.get("reality_spiderX", "/")
        stream["realitySettings"] = reality_conf

    new_inbound["streamSettings"] = stream

    # Fallbacks for vless/trojan + TCP 
    if protocol in ["vless", "trojan"] and net in ["raw", "tcp"]:
        fallback = {
            "name": request.form.get("fallback_sni", ""),
            "alpn": request.form.get("fallback_alpn", ""),
            "path": request.form.get("fallback_path", "")
        }
        try:
            fallback["dest"] = int(request.form.get("fallback_dest", "0"))
        except:
            fallback["dest"] = 0
        try:
            fallback["xver"] = int(request.form.get("fallback_xver", "0"))
        except:
            fallback["xver"] = 0
        new_inbound["fallbacks"] = [fallback]

    # Sniffing
    sniffing_enabled = (request.form.get("sniffing") == "on")
    dest_override = request.form.getlist("dest_override[]")
    new_inbound["sniffing"] = {
        "enabled": sniffing_enabled,
        "destOverride": dest_override,
        "metadataOnly": (request.form.get("metadata_only") == "on"),
        "domainsExcluded": [
            s.strip() for s in request.form.get("domains_excluded", "").split(",") if s.strip()
        ],
        "routeOnly": (request.form.get("route_only") == "on")
    }

    found_existing = False
    for idx, ib in enumerate(inbounds):
        if ib.get("tag") == new_inbound["tag"]:
            inbounds[idx] = new_inbound
            found_existing = True
            break
    if not found_existing:
        inbounds.append(new_inbound)

    success = update_xray_inbounds(session["token"], node_id, inbounds)
    if success:
        flash("Inbound saved successfully.")
    else:
        flash("Failed to update inbound on server.")
    return redirect(url_for("view_inbounds", node_id=node_id))

@app.route("/node/<int:node_id>/delete_inbound/<path:inbound_tag>")
def delete_inbound(node_id, inbound_tag):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve config for deletion.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Invalid config JSON.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    inbounds = raw_json.get("inbounds", [])
    new_inbounds = [ib for ib in inbounds if ib.get("tag") != inbound_tag]
    if len(new_inbounds) == len(inbounds):
        flash("No inbound found with the specified tag.")
        return redirect(url_for("view_inbounds", node_id=node_id))

    success = update_xray_inbounds(session["token"], node_id, new_inbounds)
    if success:
        flash(f"Inbound '{inbound_tag}' deleted.")
    else:
        flash("Failed to update config after deletion.")
    return redirect(url_for("view_inbounds", node_id=node_id))

#############################
# bulk delete inbounds
#############################
@app.route("/node/<int:node_id>/bulk_delete_inbounds/", methods=["POST"])
def bulk_delete_inbounds(node_id):
    """Deletes multiple inbounds by their tags in a single request."""
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "tags" not in data:
        return jsonify({"error": "No tags provided"}), 400

    tags_to_delete = data["tags"]
    if not isinstance(tags_to_delete, list):
        return jsonify({"error": "'tags' must be a list"}), 400

    # Fetch existing config
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        return jsonify({"error": "Failed to retrieve Xray config"}), 400

    try:
        raw_json = json.loads(config_data["config"])
    except Exception as e:
        return jsonify({"error": "Cannot parse Xray config", "details": str(e)}), 400

    inbounds = raw_json.get("inbounds", [])

    # Filter out any inbound whose tag is in tags_to_delete
    new_inbounds = [ib for ib in inbounds if ib.get("tag") not in tags_to_delete]

    # If no inbounds changed, respond accordingly
    if len(new_inbounds) == len(inbounds):
        return jsonify({
            "error": "No matching inbound tags found to delete."
        }), 400

    # Save updated inbounds to the config
    success = update_xray_inbounds(session["token"], node_id, new_inbounds)
    if not success:
        return jsonify({"error": "Failed to update config after bulk deletion"}), 500

    return jsonify({"success": True})

#############################
###############################################################################
#                           OUTBOUND ROUTES                                   #
###############################################################################
@app.route("/node/<int:node_id>/outbounds")
def outbounds(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve Xray config for outbounds.")
        return redirect(url_for("show_nodes"))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Invalid Xray config JSON.")
        return redirect(url_for("show_nodes"))

    outbounds = raw_json.get("outbounds", [])
    return render_template("outbounds.html", node_id=node_id, outbounds=outbounds)

@app.route("/node/<int:node_id>/add_outbound")
def add_outbound(node_id):
    if "token" not in session:
        return redirect("/")
    outbound_data = {}
    outbound_data_json = json.dumps(outbound_data)

    protocols = [
        "freedom", "blackhole", "dns", "vmess", "vless", "trojan",
        "shadowsocks", "socks", "http", "wireguard"
    ]
    freedom_strategies = ["AsIs", "UseIP", "UseIPv4", "UseIPv6", "ForceIP"]
    stream_transmissions = ["tcp", "ws", "grpc", "httpupgrade", "xhttp", "raw", "mKCP"]

    default_tag = f"outbound-{random.randint(1000, 9999)}"

    return render_template(
        "outbound_form.html",
        page_title="Add Outbound",
        form_action_url=url_for("save_outbound", node_id=node_id),
        outbound_data_json=outbound_data_json,
        protocols=protocols,
        freedomDomainStrategies=freedom_strategies,
        stream_transmissions=stream_transmissions,
        node_id=node_id,
        default_tag=default_tag,
        edit_mode=False
    )

@app.route("/node/<int:node_id>/edit_outbound/<path:outbound_tag>")
def edit_outbound(node_id, outbound_tag):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve config.")
        return redirect(url_for("outbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Invalid config JSON.")
        return redirect(url_for("outbounds", node_id=node_id))

    outbounds = raw_json.get("outbounds", [])
    outbound_data = None
    for ob in outbounds:
        if ob.get("tag") == outbound_tag:
            outbound_data = ob
            break
    if not outbound_data:
        flash(f"No outbound found with tag: {outbound_tag}")
        return redirect(url_for("outbounds", node_id=node_id))

    outbound_data_json = json.dumps(outbound_data, indent=2)

    protocols = [
        "freedom", "blackhole", "dns", "vmess", "vless", "trojan",
        "shadowsocks", "socks", "http", "wireguard"
    ]
    freedom_strategies = ["AsIs", "UseIP", "UseIPv4", "UseIPv6", "ForceIP"]
    stream_transmissions = ["tcp", "ws", "grpc", "httpupgrade", "xhttp", "raw", "mKCP"]

    return render_template(
        "outbound_form.html",
        page_title=f"Edit Outbound (tag: {outbound_tag})",
        form_action_url=url_for("save_outbound", node_id=node_id),
        outbound_data_json=outbound_data_json,
        protocols=protocols,
        freedomDomainStrategies=freedom_strategies,
        stream_transmissions=stream_transmissions,
        node_id=node_id,
        default_tag=outbound_tag,
        edit_mode=True
    )

@app.route("/node/<int:node_id>/save_outbound", methods=["POST"])
def save_outbound(node_id):
    if "token" not in session:
        return redirect("/")

    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Cannot retrieve config for outbounds update.")
        return redirect(url_for("outbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Config JSON parse error.")
        return redirect(url_for("outbounds", node_id=node_id))

    outbounds = raw_json.get("outbounds", [])

    # We'll look for the entire JSON in "jsonEditor"
    outbound_str = request.form.get("jsonEditor", "")
    if not outbound_str:
        flash("No outbound JSON provided.")
        return redirect(url_for("outbounds", node_id=node_id))

    try:
        new_outbound = json.loads(outbound_str)
    except:
        flash("Cannot parse posted Outbound JSON.")
        return redirect(url_for("outbounds", node_id=node_id))

    new_tag = new_outbound.get("tag", "")
    if not new_tag:
        flash("Outbound must have a valid 'tag'.")
        return redirect(url_for("outbounds", node_id=node_id))

    found_existing = False
    for idx, ob in enumerate(outbounds):
        if ob.get("tag") == new_tag:
            outbounds[idx] = new_outbound
            found_existing = True
            break
    if not found_existing:
        outbounds.append(new_outbound)

    success = update_xray_outbounds(session["token"], node_id, outbounds)
    if success:
        flash("Outbound saved successfully.")
    else:
        flash("Failed to update outbound on server.")
    return redirect(url_for("outbounds", node_id=node_id))

@app.route("/node/<int:node_id>/delete_outbound/<path:outbound_tag>")
def delete_outbound(node_id, outbound_tag):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve config for deletion.")
        return redirect(url_for("outbounds", node_id=node_id))

    try:
        raw_json = json.loads(config_data["config"])
    except:
        flash("Invalid config JSON.")
        return redirect(url_for("outbounds", node_id=node_id))

    outbounds = raw_json.get("outbounds", [])
    new_outbounds = [ob for ob in outbounds if ob.get("tag") != outbound_tag]
    if len(new_outbounds) == len(outbounds):
        flash(f"No outbound found with tag: {outbound_tag}")
        return redirect(url_for("outbounds", node_id=node_id))

    success = update_xray_outbounds(session["token"], node_id, new_outbounds)
    if success:
        flash(f"Outbound '{outbound_tag}' deleted.")
    else:
        flash("Failed to update config after deletion.")
    return redirect(url_for("outbounds", node_id=node_id))

###############################################################################
#                     RULES & DNS (Placeholder) ROUTES                        #
###############################################################################
@app.route("/node/<int:node_id>/rules")
def rules(node_id):
    if "token" not in session:
        return redirect("/")
    mock_rules = [
        {
            "type": "field",
            "outboundTag": "example-outbound",
            "domain": "example.com,test.com",
            "domainMatcher": "",
            "source": "",
            "sourcePort": "",
            "network": "",
            "protocol": [],
            "attrs": [],
            "ip": "",
            "user": "",
            "port": "",
            "inboundTag": []
        }
    ]
    # Pass actual tag arrays
    inbound_tags = ["tagA", "tagB", "tagC"]
    outbound_tags = ["tagX", "tagY", "tagZ"]
    balancer_tags = ["balancer1", "balancer2"]
    return render_template("rules.html", node_id=node_id, rules=mock_rules,
                           inbound_tags=inbound_tags, outbound_tags=outbound_tags,
                           balancer_tags=balancer_tags)

# get tags
@app.route("/node/<int:node_id>/tags")
def get_tags(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        return jsonify({"error": "No config"}), 400
    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        return jsonify({"error": "Config parse error", "message": str(e)}), 400

    # Extract inbound tags from inbounds (if defined)
    inbound_tags = []
    if "inbounds" in config:
        for inbound in config["inbounds"]:
            tag = inbound.get("tag")
            if tag and tag not in inbound_tags:
                inbound_tags.append(tag)

    # Extract outbound tags from outbounds
    outbound_tags = []
    if "outbounds" in config:
        for outbound in config["outbounds"]:
            tag = outbound.get("tag")
            if tag and tag not in outbound_tags:
                outbound_tags.append(tag)

    # Extract balancer tags (if any, from routing.balancers)
    balancer_tags = []
    if "routing" in config and "balancers" in config["routing"]:
        for balancer in config["routing"]["balancers"]:
            tag = balancer.get("tag")
            if tag and tag not in balancer_tags:
                balancer_tags.append(tag)

    return jsonify({
        "inbound_tags": inbound_tags,
        "outbound_tags": outbound_tags,
        "balancer_tags": balancer_tags
    })

# rules view
@app.route("/node/<int:node_id>/rules")
def rules_view(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    existing_rules = []
    try:
        config = json.loads(config_data["config"])
        if "routing" in config and "rules" in config["routing"]:
            existing_rules = config["routing"]["rules"]
    except Exception as e:
        print("Error parsing config:", e)
    return render_template("rules.html", node_id=node_id, rules=existing_rules)

@app.route("/node/<int:node_id>/rules_data")
def rules_data(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    config_data = get_xray_config(session["token"], node_id)
    existing_rules = []
    try:
        config = json.loads(config_data["config"])
        if "routing" in config and "rules" in config["routing"]:
            existing_rules = config["routing"]["rules"]
    except Exception as e:
        print("Error parsing config:", e)
    return jsonify({"rules": existing_rules})

# save the rule :|
@app.route("/node/<int:node_id>/save_rules", methods=["POST"])
def save_rules(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        return jsonify({"error": "No config available"}), 400
    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        return jsonify({"error": "Config parse error", "message": str(e)}), 400

    new_rules = request.get_json().get("rules")
    if new_rules is None:
        return jsonify({"error": "No rules provided"}), 400

    if "routing" not in config:
        config["routing"] = {}
    config["routing"]["rules"] = new_rules  # The new rules block (without internal ids)

    updated_str = json.dumps(config, indent=2)
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {session['token']}",
        "Content-Type": "application/json"
    }
    body = {
        "config": updated_str,
        "format": 1
    }
    try:
        put_resp = api_session.put(url, headers=headers, data=json.dumps(body))
        if put_resp.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Update failed", "status": put_resp.status_code}), 400
    except Exception as e:
        return jsonify({"error": "Exception during update", "message": str(e)}), 500

###############################################################################
#                   ADDITIONAL UTILITY ROUTES (CERT, etc.)                    #
###############################################################################
@app.route("/generate_cert", methods=["POST"])
def generate_cert():
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"SelfSigned"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"xray.com"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode("utf-8")
    return jsonify({"certificate": cert_pem, "private_key": key_pem})

@app.route("/generate_reality_keys", methods=["POST"])
def generate_reality_keys():
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    private_key_b64 = base64.urlsafe_b64encode(priv_bytes).rstrip(b'=').decode('utf-8')
    public_key_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode('utf-8')
    return jsonify({"private_key": private_key_b64, "public_key": public_key_b64})

@app.route("/generate_shortids", methods=["POST"])
def generate_shortids():
    short_ids = [secrets.token_hex(4) for _ in range(8)]
    return jsonify({"short_ids": ",".join(short_ids)})

##############
############## Xray reverse
def search_tag_in_value(value, tags_to_remove):
    """
    Recursively searches for any of the tags_to_remove within a value (dict, list, str, etc.).
    Returns True if a tag is found, False otherwise.
    """
    if isinstance(value, str):
        return value in tags_to_remove
    elif isinstance(value, list):
        return any(search_tag_in_value(item, tags_to_remove) for item in value)
    elif isinstance(value, dict):
        return any(search_tag_in_value(val, tags_to_remove) for val in value.values())
    return False

def update_xray_reverse(token, node_id, new_reverse, new_rules=None, rules_to_remove=None):
    """
    Updates the Xray config's reverse section and meticulously removes all routing rules
    related to the tags in rules_to_remove, searching every field in routing.rules.

    Args:
        token (str): Authentication token.
        node_id (int): Node identifier.
        new_reverse (dict): New reverse configuration (bridges and portals).
        new_rules (list, optional): New routing rules to append.
        rules_to_remove (list, optional): List of tags whose related rules should be removed.
    """
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    current = get_xray_config(token, node_id)
    if not current or "config" not in current:
        print(f"Node {node_id}: Failed to fetch current config")
        return False
    
    try:
        decoded = json.loads(current["config"])
        print(f"Node {node_id}: Current config loaded:", json.dumps(decoded, indent=2))
    except Exception as e:
        print(f"Node {node_id}: Error parsing existing config:", e)
        return False
    
    # Handle reverse section: set or remove
    if new_reverse is None or (not new_reverse.get("bridges") and not new_reverse.get("portals")):
        decoded.pop("reverse", None)
        print(f"Node {node_id}: Removed reverse section as it's empty")
    else:
        decoded["reverse"] = new_reverse
        print(f"Node {node_id}: Updated reverse section:", json.dumps(new_reverse, indent=2))
    
    # Update routing rules only
    routing = decoded.get("routing", {"rules": []})
    current_rules = routing.get("rules", [])
    print(f"Node {node_id}: Current rules before update:", json.dumps(current_rules, indent=2))
    
    # Process rules to remove (focus on routing.rules only)
    rules_to_remove = rules_to_remove if rules_to_remove is not None else []
    if rules_to_remove:
        print(f"Node {node_id}: Tags to remove:", rules_to_remove)
        updated_rules = []
        for rule in current_rules:
            # Search the entire rule structure recursively for any tag match
            should_remove = search_tag_in_value(rule, rules_to_remove)
            if not should_remove:
                updated_rules.append(rule)
            else:
                print(f"Node {node_id}: Removing rule:", json.dumps(rule, indent=2))
        current_rules = updated_rules
        print(f"Node {node_id}: Rules after removal:", json.dumps(current_rules, indent=2))
    
    # Append new rules if provided
    if new_rules:
        print(f"Node {node_id}: New rules to append:", json.dumps(new_rules, indent=2))
        current_rules.extend(new_rules)
    
    # Update the routing section
    decoded["routing"]["rules"] = current_rules
    
    updated_str = json.dumps(decoded, indent=2)
    body = {"config": updated_str, "format": 1}
    try:
        put_resp = api_session.put(url, headers=headers, data=json.dumps(body))
        print(f"Node {node_id}: PUT response status: {put_resp.status_code}")
        print(f"Node {node_id}: Updated config sent:", updated_str)
        if put_resp.status_code != 200:
            print(f"Node {node_id}: PUT response body:", put_resp.text)
        return put_resp.status_code == 200
    except Exception as e:
        print(f"Node {node_id}: Error updating reverse config:", e)
        return False

@app.route("/node/<int:node_id>/save_reverse", methods=["POST"])
def save_reverse(node_id):
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
    
    new_reverse = data.get("reverse", {"bridges": [], "portals": []})
    new_rules = data.get("newRules", [])
    rules_to_remove = data.get("rulesToRemove", [])
    
    print(f"Node {node_id}: Received payload:", json.dumps(data, indent=2))
    
    # Fetch current config
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        print(f"Node {node_id}: Config not found")
        return jsonify({"error": "Config not found"}), 400
    
    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        print(f"Node {node_id}: Config parse error:", e)
        return jsonify({"error": "Config parse error", "message": str(e)}), 400
    
    success = update_xray_reverse(
        session["token"],
        node_id,
        new_reverse if (new_reverse.get("bridges") or new_reverse.get("portals")) else None,
        new_rules,
        rules_to_remove
    )
    
    if success:
        print(f"Node {node_id}: Reverse settings updated successfully")
        return jsonify({"success": True, "message": "Reverse settings updated successfully"})
    else:
        print(f"Node {node_id}: Failed to update reverse settings")
        return jsonify({"error": "Failed to update reverse settings"}), 500

@app.route("/node/<int:node_id>/reverse")
def reverse_settings(node_id):
    if "token" not in session:
        return redirect("/")
    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Failed to retrieve Xray config.")
        return redirect(url_for("show_nodes"))
    
    try:
        config = json.loads(config_data["config"])
    except Exception as e:
        flash("Config parse error.")
        return redirect(url_for("show_nodes"))
    
    reverse_config = config.get("reverse", {"bridges": [], "portals": []})
    inbounds = config.get("inbounds", [])
    outbounds = config.get("outbounds", [])
    routing = config.get("routing", {"rules": []})
    
    inbound_tags = [ib.get("tag") for ib in inbounds if ib.get("tag")]
    outbound_tags = [ob.get("tag") for ob in outbounds if ob.get("tag")]
    
    return render_template(
        "reverse.html",
        node_id=node_id,
        reverse_config=json.dumps(reverse_config),
        inbound_tags=inbound_tags,
        outbound_tags=outbound_tags,
        routing_rules=routing.get("rules", [])
    )

##############
############# ADVANCED SECTION ############
###################
@app.route("/node/<int:node_id>/advance", methods=["GET"])
def advanced_editor(node_id):
    """
    Loads the entire Xray config from the API, double-escapes it into a valid JSON string,
    and passes it to 'advance.html' for editing in Vue.
    """
    if "token" not in session:
        return redirect("/")

    config_data = get_xray_config(session["token"], node_id)
    if not config_data or "config" not in config_data:
        flash("Xray config not found.")
        return redirect(url_for("show_nodes"))

    # The raw Xray config as a string
    raw_config = config_data["config"]

    # Double-escape into a valid JSON string literal
    escaped_config = json.dumps(raw_config)

    # Render the Vue-based template
    return render_template("advance.html", node_id=node_id, config_str=escaped_config)

@app.route("/node/<int:node_id>/advance_save", methods=["POST"])
def advanced_editor_save(node_id):
    """
    Finalizes and saves the entire Xray config to your backend API.
    Expects JSON data: {"config": "<full JSON string>"}
    """
    if "token" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or "config" not in data:
        return jsonify({"error": "No config provided"}), 400

    new_config_str = data["config"]

    # Optional: Verify it's valid JSON
    try:
        loaded = json.loads(new_config_str)
    except Exception as e:
        return jsonify({"error": "Invalid JSON", "message": str(e)}), 400

    # Now PUT it back to the Xray config
    url = f"{API_BASE_URL}/nodes/{node_id}/xray/config"
    headers = {
        "Authorization": f"Bearer {session['token']}",
        "Content-Type": "application/json"
    }
    body = {
        "config": json.dumps(loaded, indent=2),
        "format": 1
    }
    try:
        resp = api_session.put(url, headers=headers, data=json.dumps(body))
        if resp.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({
                "error": "Update failed",
                "status_code": resp.status_code
            }), 400
    except Exception as e:
        return jsonify({"error": "Exception during update", "message": str(e)}), 500

###############################################################################
#                               MAIN ENTRY                                    #
###############################################################################
if __name__ == "__main__":
    app.register_blueprint(getinfo_bp)
    if USE_HTTPS and CERT_FILE and KEY_FILE:
        ssl_context = (CERT_FILE, KEY_FILE)
        print(f"Starting HTTPS server on https://{DOMAIN or HOST}:{PORT}")
        app.run(host=HOST, port=PORT, debug=False, ssl_context=ssl_context)
    else:
        print(f"Starting HTTP server on http://{HOST}:{PORT}")
        app.run(host=HOST, port=PORT, debug=False)
