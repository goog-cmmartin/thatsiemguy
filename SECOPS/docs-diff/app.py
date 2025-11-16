from flask import Flask, jsonify, render_template, request
import sqlite3
from datetime import datetime
from config import DB_NAME, DOC_SOURCES

app = Flask(__name__)

def get_db_connection():
    """Creates a database connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Serves the main HTML page, passing DOC_SOURCES and product icons to the template."""
    product_icons = {
        "Chronicle": "static/SecOps-512-color-rgb.png",
        "Security Command Center": "static/SecurityCommandCenter-512-color.png",
        "GCP Cloud IDS": "static/Networking-512-color.png",
        "GCP Cloud Logging": "static/Operations-512-color.png",
        "GCP Cloud Monitoring": "static/Operations-512-color.png"
    }
    return render_template('index.html', doc_sources=DOC_SOURCES, product_icons=product_icons)

@app.route('/broken-links')
def broken_links():
    """Serves the broken links page."""
    return render_template('broken_links.html')

@app.route('/api/broken_links')
def get_broken_links():
    """API endpoint to fetch broken links data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT scrape_date, source_url, target_url FROM broken_links ORDER BY scrape_date DESC")
    links = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(links)


@app.route('/api/reports')
def get_reports():
    """API endpoint to fetch report data from the database, with optional filtering."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    product_filter = request.args.get('product')
    change_type_filter = request.args.get('change_type')
    sort_order = request.args.get('sort', 'DESC').upper()
    search_query = request.args.get('search')
    log_id = request.args.get('log_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    if log_id:
        # If a specific log_id is requested, override all other filters
        query = "SELECT log_id, scrape_date, url, change_type, summary, summary as plain_summary, source_tag FROM change_log WHERE log_id = ?"
        params = [log_id]
    else:
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'

        if not end_date_str:
            cursor.execute("SELECT MAX(scrape_date) FROM change_log")
            latest_date = cursor.fetchone()[0]
            end_date_str = latest_date if latest_date else datetime.now().strftime('%Y-%m-%d')
        
        if not start_date_str:
            start_date_str = end_date_str

        params = [start_date_str, end_date_str]
        
        if search_query:
            query = f"""
                SELECT 
                    cl.log_id,
                    cl.scrape_date, 
                    cl.url, 
                    cl.change_type, 
                    highlight(change_log_fts, 0, '<mark>', '</mark>') as summary,
                    cl.summary as plain_summary,
                    cl.source_tag
                FROM change_log cl
                JOIN change_log_fts fts ON cl.log_id = fts.rowid
                WHERE fts.summary MATCH ?
                AND cl.scrape_date BETWEEN ? AND ?
            """
            params.insert(0, search_query + '*')
        else:
            query = f"""
                SELECT log_id, scrape_date, url, change_type, summary, summary as plain_summary, source_tag 
                FROM change_log 
                WHERE scrape_date BETWEEN ? AND ?
            """
            # Only show summarized items unless specifically filtering for 'new'
            if change_type_filter != 'new':
                query += " AND summary IS NOT NULL"

        if product_filter:
            query += " AND source_tag = ?"
            params.append(product_filter)

        if change_type_filter:
            query += " AND change_type = ?"
            params.append(change_type_filter)
        elif not search_query:
            # Default to not showing 'unchanged' if no specific change type is requested
            query += " AND change_type != 'unchanged'"

        query += f" ORDER BY scrape_date {sort_order}, url ASC"
    
    cursor.execute(query, tuple(params))
    
    reports = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify(reports)

@app.route('/api/products')
def get_products():
    """API endpoint to fetch a list of unique product source tags."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT source_tag FROM change_log WHERE source_tag IS NOT NULL AND source_tag != '' ORDER BY source_tag")
    products = [row['source_tag'] for row in cursor.fetchall()]
    conn.close()
    return jsonify(products)

@app.route('/api/last_updated')
def get_last_updated():
    """API endpoint to get the last scrape date."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(scrape_date) FROM change_log")
    last_updated = cursor.fetchone()[0]
    conn.close()
    return jsonify({'last_updated': last_updated})

@app.route('/api/activity')
def get_activity_data():
    """API endpoint for chart data, with optional product and date filtering."""
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    product_filter = request.args.get('product')
    change_type_filter = request.args.get('change_type')

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT scrape_date, 
               SUM(CASE WHEN change_type = 'new' THEN 1 ELSE 0 END) as new_count,
               SUM(CASE WHEN change_type = 'updated' THEN 1 ELSE 0 END) as updated_count
        FROM change_log
    """
    params = []
    where_clauses = ["change_type != 'unchanged'"]

    if start_date_str and end_date_str:
        where_clauses.append("scrape_date BETWEEN ? AND ?")
        params.extend([start_date_str, end_date_str])
    
    if product_filter:
        where_clauses.append("source_tag = ?")
        params.append(product_filter)

    if change_type_filter:
        where_clauses.append("change_type = ?")
        params.append(change_type_filter)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " GROUP BY scrape_date ORDER BY scrape_date ASC"
    
    cursor.execute(query, tuple(params))
    
    data = cursor.fetchall()
    conn.close()

    chart_data = {
        'labels': [row['scrape_date'] for row in data],
        'datasets': [
            {'label': 'New Items', 'data': [row['new_count'] for row in data], 'backgroundColor': 'rgba(40, 167, 69, 0.7)'},
            {'label': 'Updated Items', 'data': [row['updated_count'] for row in data], 'backgroundColor': 'rgba(0, 123, 255, 0.7)'}
        ]
    }
    return jsonify(chart_data)


if __name__ == '__main__':
    app.run(debug=True)
