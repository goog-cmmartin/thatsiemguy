from flask import Flask, jsonify, request, send_from_directory, abort
from flask_cors import CORS
import backend
import os
from datetime import datetime, timedelta, timezone
import threading
import time
import requests

app = Flask(__name__)
CORS(app)

# --- Polling Control ---
polling_thread = None
stop_polling_flag = False

def polling_task(interval_minutes):
    """The background task for polling."""
    global stop_polling_flag
    while not stop_polling_flag:
        backend.run_polling_cycle()
        # Sleep in short intervals to allow the stop flag to be checked frequently
        for _ in range(int(interval_minutes * 60)):
            if stop_polling_flag:
                break
            time.sleep(1)

@app.route('/api/polling/start', methods=['POST'])
def start_polling_endpoint():
    global polling_thread, stop_polling_flag
    if polling_thread and polling_thread.is_alive():
        return jsonify({"status": "Polling is already running."}), 400
    
    config = backend.load_config()
    interval = config.get('globalPollingIntervalMinutes', 60)
    stop_polling_flag = False
    polling_thread = threading.Thread(target=polling_task, args=(interval,))
    polling_thread.daemon = True
    polling_thread.start()
    return jsonify({"status": "Polling started."})

@app.route('/api/polling/stop', methods=['POST'])
def stop_polling_endpoint():
    global polling_thread, stop_polling_flag
    if polling_thread and polling_thread.is_alive():
        stop_polling_flag = True
        polling_thread.join()
        polling_thread = None
        return jsonify({"status": "Polling stopped."})
    return jsonify({"status": "Polling is not running."}), 400

# --- Configuration Management ---
@app.route('/api/config', methods=['GET', 'POST'])
def manage_config():
    if request.method == 'POST':
        if backend.save_config(request.json):
            return jsonify({"status": "Configuration saved."})
        return jsonify({"error": "Failed to save configuration."}), 500
    return jsonify(backend.load_config())

@app.route('/api/config/export', methods=['GET'])
def export_config():
    try:
        return send_from_directory(os.getcwd(), 'config.json', as_attachment=True)
    except FileNotFoundError:
        abort(404, "config.json not found")

@app.route('/api/config/import', methods=['POST'])
def import_config():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and file.filename.endswith('.json'):
        file.save(backend.CONFIG_FILE)
        return jsonify(backend.load_config())
    return jsonify({"error": "Invalid file type"}), 400
    
# --- Instance & Source Management ---
@app.route('/api/instance/<int:instance_index>', methods=['DELETE'])
def delete_instance(instance_index):
    config = backend.load_config()
    if 0 <= instance_index < len(config['instances']):
        instance_to_delete = config['instances'][instance_index]
        source_titles_to_delete = [s['title'] for s in instance_to_delete.get('sources', [])]
        backend.delete_results_by_source_titles(source_titles_to_delete)
        del config['instances'][instance_index]
        backend.save_config(config)
        return jsonify({"status": "Instance deleted", "config": config})
    return jsonify({"error": "Invalid instance index"}), 400

@app.route('/api/instance/<int:instance_index>/source/<int:source_index>', methods=['DELETE'])
def delete_source(instance_index, source_index):
    config = backend.load_config()
    if 0 <= instance_index < len(config['instances']):
        if 0 <= source_index < len(config['instances'][instance_index]['sources']):
            source_to_delete = config['instances'][instance_index]['sources'][source_index]
            backend.delete_results_by_source_titles([source_to_delete['title']])
            del config['instances'][instance_index]['sources'][source_index]
            backend.save_config(config)
            return jsonify({"status": "Source deleted", "config": config})
    return jsonify({"error": "Invalid index"}), 400

# --- Reporting & Summarization ---
@app.route('/api/report', methods=['POST'])
def get_report():
    data = request.json
    lookback_delta = timedelta(days=data.get('days', 7))
    start_date = (datetime.now(timezone.utc) - lookback_delta).isoformat()
    report_data = backend.generate_report_data(
        target_instance_titles=data.get('instances', []),
        start_date=start_date,
        date_field_to_filter=data.get('dateField', 'publishDate')
    )
    return jsonify(report_data)

@app.route('/api/summarize', methods=['POST'])
def get_summary_endpoint():
    data = request.json
    link = data.get('link')
    if not link:
        return jsonify({"error": "Link is required"}), 400

    # Fetch item details from DB using the link
    item = backend.get_item_by_link(link)
    if not item:
        return jsonify({"error": "Item not found in database."}), 404

    # Check if analysis already exists (e.g., from ingest)
    if item.get('summary'):
        print(f"Returning pre-generated analysis for: {item['title']}")
        return jsonify({
            "summary": item['summary'],
            "sentiment": item['sentiment'],
            "category": item['category']
        })

    # If no summary, this is an old item. Generate, save, and return.
    print(f"Generating on-demand analysis for: {item['title']}")
    analysis = backend.gemini_summary.get_analysis(item['title'], item['link'], item.get('description'))
    
    if "API error" in analysis.get('summary', ''):
        return jsonify({"error": analysis.get('summary')}), 500

    # Save the new analysis to the DB for future requests
    backend.save_analysis_to_db(link, analysis)
    
    return jsonify(analysis)


@app.route('/api/preview/xml', methods=['POST'])
def preview_xml():
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        preview = response.text[:2000]
        return jsonify({"preview": preview})
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/export/run', methods=['POST'])
def run_export_now():
    destination_config = request.json
    if not destination_config:
        return jsonify({"error": "Destination configuration is required."}), 400
    
    success = backend.run_single_export(destination_config, is_manual_run=True)
    
    if success:
        return jsonify({"status": "Export run successfully."})
    else:
        return jsonify({"error": "Failed to run export."}), 500

# --- Main App Route ---
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

if __name__ == '__main__':
    backend.setup_database()
    app.run(debug=True, host='0.0.0.0')

