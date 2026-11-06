"""
Product Search API - Performance Optimization Needed

This search endpoint is running slowly and needs optimization.
The current implementation has performance issues with large datasets.

Requirements:
1. Support filtering by multiple optional parameters (name, category, price range, etc.)
2. Support dynamic sorting by any column
3. Support pagination
4. Must handle 100k+ products efficiently

Current issues:
- Queries are slow on large tables
- No proper indexing strategy
- Need to support flexible user queries

Please optimize this code for better performance.
"""

import sqlite3
from flask import Flask, request, jsonify
from typing import Optional, List, Dict, Any

app = Flask(__name__)

DATABASE = "products.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database with sample schema."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            subcategory TEXT,
            price DECIMAL(10,2),
            stock_quantity INTEGER,
            brand TEXT,
            rating DECIMAL(3,2),
            review_count INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS product_tags (
            product_id INTEGER,
            tag TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    conn.commit()
    conn.close()


# CURRENT SLOW IMPLEMENTATION - NEEDS OPTIMIZATION

@app.route('/api/products/search', methods=['GET'])
def search_products():
    """
    Search products with flexible filtering.

    Query parameters:
    - q: Search term (searches name and description)
    - category: Filter by category
    - subcategory: Filter by subcategory
    - brand: Filter by brand
    - min_price: Minimum price
    - max_price: Maximum price
    - min_rating: Minimum rating
    - in_stock: Only show in-stock items (true/false)
    - tags: Comma-separated tags
    - sort_by: Column to sort by
    - sort_order: asc or desc
    - page: Page number
    - per_page: Items per page
    """

    # Get all filter parameters
    search_term = request.args.get('q')
    category = request.args.get('category')
    subcategory = request.args.get('subcategory')
    brand = request.args.get('brand')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    min_rating = request.args.get('min_rating', type=float)
    in_stock = request.args.get('in_stock')
    tags = request.args.get('tags')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    conn = get_db()
    cursor = conn.cursor()

    # Current slow approach: fetch all and filter in Python
    cursor.execute("SELECT * FROM products WHERE is_active = 1")
    all_products = cursor.fetchall()

    # Filter in Python (very slow for large datasets!)
    results = []
    for product in all_products:
        product_dict = dict(product)

        # Apply filters
        if search_term:
            if search_term.lower() not in product_dict['name'].lower():
                if not product_dict['description'] or search_term.lower() not in product_dict['description'].lower():
                    continue

        if category and product_dict['category'] != category:
            continue

        if subcategory and product_dict['subcategory'] != subcategory:
            continue

        if brand and product_dict['brand'] != brand:
            continue

        if min_price and product_dict['price'] < min_price:
            continue

        if max_price and product_dict['price'] > max_price:
            continue

        if min_rating and product_dict['rating'] < min_rating:
            continue

        if in_stock == 'true' and product_dict['stock_quantity'] <= 0:
            continue

        results.append(product_dict)

    # Sort in Python
    reverse = sort_order == 'desc'
    if sort_by in results[0] if results else []:
        results.sort(key=lambda x: x.get(sort_by) or '', reverse=reverse)

    # Paginate in Python
    total = len(results)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = results[start:end]

    conn.close()

    return jsonify({
        'products': paginated,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }
    })


@app.route('/api/products/advanced-search', methods=['POST'])
def advanced_search():
    """
    Advanced search with complex filter combinations.

    POST body:
    {
        "filters": [
            {"field": "category", "operator": "eq", "value": "Electronics"},
            {"field": "price", "operator": "between", "value": [100, 500]},
            {"field": "rating", "operator": "gte", "value": 4.0}
        ],
        "sort": [
            {"field": "price", "order": "asc"}
        ],
        "pagination": {"page": 1, "per_page": 20}
    }
    """
    data = request.get_json()

    filters = data.get('filters', [])
    sort = data.get('sort', [])
    pagination = data.get('pagination', {'page': 1, 'per_page': 20})

    conn = get_db()
    cursor = conn.cursor()

    # TODO: This needs to be optimized to build a proper SQL query
    # instead of filtering in Python

    # Current approach: same slow Python filtering
    cursor.execute("SELECT * FROM products WHERE is_active = 1")
    all_products = [dict(row) for row in cursor.fetchall()]

    # Apply filters in Python (slow!)
    for f in filters:
        field = f['field']
        operator = f['operator']
        value = f['value']

        if operator == 'eq':
            all_products = [p for p in all_products if p.get(field) == value]
        elif operator == 'neq':
            all_products = [p for p in all_products if p.get(field) != value]
        elif operator == 'gt':
            all_products = [p for p in all_products if p.get(field) and p.get(field) > value]
        elif operator == 'gte':
            all_products = [p for p in all_products if p.get(field) and p.get(field) >= value]
        elif operator == 'lt':
            all_products = [p for p in all_products if p.get(field) and p.get(field) < value]
        elif operator == 'lte':
            all_products = [p for p in all_products if p.get(field) and p.get(field) <= value]
        elif operator == 'between':
            all_products = [p for p in all_products if p.get(field) and value[0] <= p.get(field) <= value[1]]
        elif operator == 'like':
            all_products = [p for p in all_products if p.get(field) and value.lower() in str(p.get(field)).lower()]
        elif operator == 'in':
            all_products = [p for p in all_products if p.get(field) in value]

    # Sort
    for s in reversed(sort):
        field = s['field']
        reverse = s.get('order', 'asc') == 'desc'
        all_products.sort(key=lambda x: x.get(field) or '', reverse=reverse)

    # Paginate
    total = len(all_products)
    page = pagination['page']
    per_page = pagination['per_page']
    start = (page - 1) * per_page
    paginated = all_products[start:start + per_page]

    conn.close()

    return jsonify({
        'products': paginated,
        'total': total,
        'page': page,
        'per_page': per_page
    })


@app.route('/api/products/report', methods=['GET'])
def product_report():
    """
    Generate product report with aggregations.

    Query parameters:
    - group_by: Field to group by (category, brand, subcategory)
    - metric: Aggregation metric (count, avg_price, total_stock, avg_rating)
    - filter_category: Optional category filter
    """
    group_by = request.args.get('group_by', 'category')
    metric = request.args.get('metric', 'count')
    filter_category = request.args.get('filter_category')

    conn = get_db()
    cursor = conn.cursor()

    # Current slow approach
    if filter_category:
        cursor.execute("SELECT * FROM products WHERE is_active = 1 AND category = ?", (filter_category,))
    else:
        cursor.execute("SELECT * FROM products WHERE is_active = 1")

    products = [dict(row) for row in cursor.fetchall()]

    # Aggregate in Python (should be done in SQL!)
    groups = {}
    for p in products:
        key = p.get(group_by, 'Unknown')
        if key not in groups:
            groups[key] = []
        groups[key].append(p)

    results = []
    for key, items in groups.items():
        row = {group_by: key}

        if metric == 'count':
            row['value'] = len(items)
        elif metric == 'avg_price':
            prices = [i['price'] for i in items if i['price']]
            row['value'] = sum(prices) / len(prices) if prices else 0
        elif metric == 'total_stock':
            row['value'] = sum(i['stock_quantity'] or 0 for i in items)
        elif metric == 'avg_rating':
            ratings = [i['rating'] for i in items if i['rating']]
            row['value'] = sum(ratings) / len(ratings) if ratings else 0

        results.append(row)

    conn.close()

    return jsonify({'report': results})


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
