from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime, timedelta
import hashlib
import secrets
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
import base64

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

DATABASE = 'kidswear_pos.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            barcode TEXT UNIQUE,
            name TEXT NOT NULL,
            category TEXT,
            subcategory TEXT,
            brand TEXT,
            size TEXT,
            color TEXT,
            cost_price REAL,
            selling_price REAL NOT NULL,
            stock INTEGER DEFAULT 0,
            min_stock INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Customers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT,
            address TEXT,
            loyalty_points INTEGER DEFAULT 0,
            membership_tier TEXT DEFAULT 'Standard',
            total_purchases REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Sales table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER,
            customer_name TEXT,
            customer_phone TEXT,
            subtotal REAL NOT NULL,
            discount_percent REAL DEFAULT 0,
            discount_amount REAL DEFAULT 0,
            gst_amount REAL NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT DEFAULT 'Paid',
            cashier_id INTEGER,
            cashier_name TEXT,
            items_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(cashier_id) REFERENCES users(id)
        )
    ''')

    # Returns table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS returns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            return_number TEXT UNIQUE NOT NULL,
            sale_id INTEGER NOT NULL,
            invoice_number TEXT NOT NULL,
            customer_name TEXT,
            return_amount REAL NOT NULL,
            reason TEXT,
            items_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sale_id) REFERENCES sales(id)
        )
    ''')

    # Suppliers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            gst_number TEXT,
            address TEXT,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Purchases table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_number TEXT UNIQUE NOT NULL,
            supplier_id INTEGER NOT NULL,
            supplier_name TEXT,
            total_amount REAL NOT NULL,
            paid_amount REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            items_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
        )
    ''')

    # Employees table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            email TEXT,
            role TEXT NOT NULL,
            salary REAL,
            joining_date DATE,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Attendance table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            date DATE NOT NULL,
            status TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY(employee_id) REFERENCES employees(id),
            UNIQUE(employee_id, date)
        )
    ''')

    # Login activity table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    # Insert default admin user
    cursor.execute("SELECT COUNT(*) FROM users WHERE username='Akshada2001'")
    if cursor.fetchone()[0] == 0:
        password_hash = hashlib.sha256('Akshada@123'.encode()).hexdigest()
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                      ('Akshada2001', password_hash, 'admin'))
    conn.commit()

# Also ensure Akshada2001 user exists
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)",
             ('Akshada2001', hashlib.sha256('Akshada@123'.encode()).hexdigest(), 'Admin'))
    # Insert sample products
    cursor.execute("SELECT COUNT(*) FROM products")
    if cursor.fetchone()[0] == 0:
        sample_products = [
            ('KW-0001', '8901234567890', 'Girls Floral Dress', 'Clothing', 'Girl', 'Little Hearts', 'M', 'Pink', 350, 699, 25),
            ('KW-0002', '8901234567891', 'Boys Cotton T-Shirt', 'Clothing', 'Boy', 'Kids Corner', 'L', 'Blue', 200, 399, 30),
            ('KW-0003', '8901234567892', 'Unisex Denim Jeans', 'Clothing', 'Unisex', 'Urban Kids', 'S', 'Dark Blue', 450, 899, 15),
            ('KW-0004', '8901234567893', 'Girls Party Frock', 'Clothing', 'Girl', 'Little Hearts', 'M', 'Red', 500, 1199, 12),
            ('KW-0005', '8901234567894', 'Boys Cargo Shorts', 'Clothing', 'Boy', 'Kids Corner', 'M', 'Khaki', 250, 499, 20),
        ]
        cursor.executemany('''INSERT INTO products
            (sku, barcode, name, category, subcategory, brand, size, color, cost_price, selling_price, stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', sample_products)

    conn.commit()
    conn.close()

# Auth endpoints
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    password_hash = hashlib.sha256(password.encode()).hexdigest()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password_hash))
    user = cursor.fetchone()

    if user:
        # Log login activity
        cursor.execute("INSERT INTO login_activity (user_id, username) VALUES (?, ?)",
                      (user['id'], user['username']))
        conn.commit()

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'role': user['role']
            }
        })
    else:
        conn.close()
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

# Dashboard endpoints
@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    conn = get_db()
    cursor = conn.cursor()

    # Today's sales
    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0) as today_sales, COUNT(*) as today_orders
        FROM sales
        WHERE DATE(created_at) = DATE('now')
    """)
    today = cursor.fetchone()

    # This month's sales
    cursor.execute("""
        SELECT COALESCE(SUM(total_amount), 0) as month_sales
        FROM sales
        WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    """)
    month = cursor.fetchone()

    # Total customers
    cursor.execute("SELECT COUNT(*) as total_customers FROM customers")
    customers = cursor.fetchone()

    # Low stock products
    cursor.execute("SELECT COUNT(*) as low_stock FROM products WHERE stock <= min_stock")
    low_stock = cursor.fetchone()

    # Top selling products
    cursor.execute("""
        SELECT p.name, p.sku, SUM(json_extract(value, '$.quantity')) as total_sold
        FROM sales s, json_each(s.items_json)
        JOIN products p ON p.id = CAST(json_extract(value, '$.product_id') AS INTEGER)
        WHERE DATE(s.created_at) >= DATE('now', '-30 days')
        GROUP BY p.id
        ORDER BY total_sold DESC
        LIMIT 5
    """)
    top_products = [dict(row) for row in cursor.fetchall()]

    # Recent sales
    cursor.execute("""
        SELECT invoice_number, customer_name, total_amount, payment_method, created_at
        FROM sales
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent_sales = [dict(row) for row in cursor.fetchall()]

    # Sales chart data (last 7 days)
    cursor.execute("""
        SELECT DATE(created_at) as date, COALESCE(SUM(total_amount), 0) as amount
        FROM sales
        WHERE DATE(created_at) >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    chart_data = [dict(row) for row in cursor.fetchall()]

    conn.close()

    return jsonify({
        'today_sales': today['today_sales'],
        'today_orders': today['today_orders'],
        'month_sales': month['month_sales'],
        'total_customers': customers['total_customers'],
        'low_stock': low_stock['low_stock'],
        'top_products': top_products,
        'recent_sales': recent_sales,
        'chart_data': chart_data
    })

# Products endpoints
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db()
    cursor = conn.cursor()

    search = request.args.get('search', '')
    if search:
        cursor.execute("""
            SELECT * FROM products
            WHERE sku LIKE ? OR barcode LIKE ? OR name LIKE ? OR brand LIKE ?
            ORDER BY created_at DESC
        """, (f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT * FROM products ORDER BY created_at DESC")

    products = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(products)

@app.route('/api/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id=?", (product_id,))
    product = cursor.fetchone()
    conn.close()

    if product:
        return jsonify(dict(product))
    return jsonify({'error': 'Product not found'}), 404

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Generate SKU
    cursor.execute("SELECT MAX(CAST(SUBSTR(sku, 4) AS INTEGER)) as max_num FROM products WHERE sku LIKE 'KW-%'")
    result = cursor.fetchone()
    next_num = (result['max_num'] or 0) + 1
    sku = f"KW-{next_num:04d}"

    try:
        cursor.execute('''
            INSERT INTO products (sku, barcode, name, category, subcategory, brand, size, color,
                                 cost_price, selling_price, stock, min_stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (sku, data.get('barcode'), data['name'], data.get('category'), data.get('subcategory'),
              data.get('brand'), data.get('size'), data.get('color'), data.get('cost_price'),
              data['selling_price'], data.get('stock', 0), data.get('min_stock', 5)))

        conn.commit()
        product_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': product_id, 'sku': sku})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE products
            SET barcode=?, name=?, category=?, subcategory=?, brand=?, size=?, color=?,
                cost_price=?, selling_price=?, stock=?, min_stock=?
            WHERE id=?
        ''', (data.get('barcode'), data['name'], data.get('category'), data.get('subcategory'),
              data.get('brand'), data.get('size'), data.get('color'), data.get('cost_price'),
              data['selling_price'], data.get('stock', 0), data.get('min_stock', 5), product_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Barcode generation endpoint
@app.route('/api/generate-barcode', methods=['POST'])
def generate_barcode_api():
    data = request.json
    barcode_type = data.get('type', 'code128')
    barcode_data = data.get('data', '')

    if not barcode_data:
        return jsonify({'error': 'Barcode data required'}), 400

    try:
        if barcode_type == 'ean13':
            bc = barcode.get('ean13', barcode_data, writer=ImageWriter())
        elif barcode_type == 'upc':
            bc = barcode.get('upca', barcode_data, writer=ImageWriter())
        else:
            bc = barcode.get('code128', barcode_data, writer=ImageWriter())

        buffer = BytesIO()
        bc.write(buffer)
        buffer.seek(0)

        barcode_base64 = base64.b64encode(buffer.getvalue()).decode()

        return jsonify({
            'success': True,
            'barcode': f'data:image/png;base64,{barcode_base64}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

# Sales endpoints
@app.route('/api/sales', methods=['GET'])
def get_sales():
    conn = get_db()
    cursor = conn.cursor()

    search = request.args.get('search', '')
    if search:
        cursor.execute("""
            SELECT * FROM sales
            WHERE invoice_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?
            ORDER BY created_at DESC
        """, (f'%{search}%', f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT * FROM sales ORDER BY created_at DESC LIMIT 100")

    sales = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(sales)

@app.route('/api/sales', methods=['POST'])
def create_sale():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Generate invoice number
    now = datetime.now()
    cursor.execute("SELECT MAX(CAST(SUBSTR(invoice_number, -5) AS INTEGER)) as max_num FROM sales WHERE invoice_number LIKE ?",
                  (f"INV-{now.strftime('%Y%m')}-%",))
    result = cursor.fetchone()
    next_num = (result['max_num'] or 0) + 1
    invoice_number = f"INV-{now.strftime('%Y%m')}-{next_num:05d}"

    try:
        # Insert sale
        cursor.execute('''
            INSERT INTO sales (invoice_number, customer_id, customer_name, customer_phone,
                             subtotal, discount_percent, discount_amount, gst_amount, total_amount,
                             payment_method, cashier_id, cashier_name, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_number, data.get('customer_id'), data.get('customer_name'), data.get('customer_phone'),
              data['subtotal'], data.get('discount_percent', 0), data.get('discount_amount', 0),
              data['gst_amount'], data['total_amount'], data['payment_method'],
              data.get('cashier_id'), data.get('cashier_name'), json.dumps(data['items'])))

        # Update product stock
        for item in data['items']:
            cursor.execute("UPDATE products SET stock = stock - ? WHERE id = ?",
                          (item['quantity'], item['product_id']))

        # Update customer loyalty points
        if data.get('customer_id'):
            points_earned = int(data['total_amount'] / 100)
            cursor.execute("UPDATE customers SET loyalty_points = loyalty_points + ?, total_purchases = total_purchases + ? WHERE id = ?",
                          (points_earned, data['total_amount'], data['customer_id']))

        conn.commit()
        sale_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': sale_id, 'invoice_number': invoice_number})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# Returns endpoints
@app.route('/api/returns', methods=['GET'])
def get_returns():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM returns ORDER BY created_at DESC LIMIT 100")
    returns = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(returns)

@app.route('/api/returns', methods=['POST'])
def create_return():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Generate return number
    now = datetime.now()
    cursor.execute("SELECT COUNT(*) as count FROM returns WHERE DATE(created_at) = DATE('now')")
    result = cursor.fetchone()
    return_number = f"RET-{now.strftime('%Y%m%d')}-{result['count'] + 1:04d}"

    try:
        # Insert return
        cursor.execute('''
            INSERT INTO returns (return_number, sale_id, invoice_number, customer_name,
                               return_amount, reason, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (return_number, data['sale_id'], data['invoice_number'], data.get('customer_name'),
              data['return_amount'], data.get('reason'), json.dumps(data['items'])))

        # Restore product stock
        for item in data['items']:
            cursor.execute("UPDATE products SET stock = stock + ? WHERE id = ?",
                          (item['quantity'], item['product_id']))

        conn.commit()
        return_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': return_id, 'return_number': return_number})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# Customers endpoints
@app.route('/api/customers', methods=['GET'])
def get_customers():
    conn = get_db()
    cursor = conn.cursor()

    search = request.args.get('search', '')
    if search:
        cursor.execute("SELECT * FROM customers WHERE name LIKE ? OR phone LIKE ? ORDER BY created_at DESC",
                      (f'%{search}%', f'%{search}%'))
    else:
        cursor.execute("SELECT * FROM customers ORDER BY created_at DESC")

    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(customers)

@app.route('/api/customers', methods=['POST'])
def create_customer():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO customers (name, phone, email, address)
            VALUES (?, ?, ?, ?)
        ''', (data['name'], data['phone'], data.get('email'), data.get('address')))

        conn.commit()
        customer_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': customer_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE customers
            SET name=?, phone=?, email=?, address=?
            WHERE id=?
        ''', (data['name'], data['phone'], data.get('email'), data.get('address'), customer_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Suppliers endpoints
@app.route('/api/suppliers', methods=['GET'])
def get_suppliers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM suppliers ORDER BY created_at DESC")
    suppliers = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(suppliers)

@app.route('/api/suppliers', methods=['POST'])
def create_supplier():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO suppliers (name, contact_person, phone, email, gst_number, address)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['name'], data.get('contact_person'), data.get('phone'),
              data.get('email'), data.get('gst_number'), data.get('address')))

        conn.commit()
        supplier_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': supplier_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
def update_supplier(supplier_id):
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE suppliers
            SET name=?, contact_person=?, phone=?, email=?, gst_number=?, address=?, balance=?
            WHERE id=?
        ''', (data['name'], data.get('contact_person'), data.get('phone'), data.get('email'),
              data.get('gst_number'), data.get('address'), data.get('balance', 0), supplier_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
def delete_supplier(supplier_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Purchases endpoints
@app.route('/api/purchases', methods=['GET'])
def get_purchases():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM purchases ORDER BY created_at DESC LIMIT 100")
    purchases = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(purchases)

@app.route('/api/purchases', methods=['POST'])
def create_purchase():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Generate purchase number
    now = datetime.now()
    cursor.execute("SELECT COUNT(*) as count FROM purchases WHERE DATE(created_at) = DATE('now')")
    result = cursor.fetchone()
    purchase_number = f"PO-{now.strftime('%Y%m%d')}-{result['count'] + 1:04d}"

    try:
        cursor.execute('''
            INSERT INTO purchases (purchase_number, supplier_id, supplier_name, total_amount,
                                 paid_amount, balance, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (purchase_number, data['supplier_id'], data['supplier_name'], data['total_amount'],
              data.get('paid_amount', 0), data['total_amount'] - data.get('paid_amount', 0),
              json.dumps(data['items'])))

        # Update supplier balance
        cursor.execute("UPDATE suppliers SET balance = balance + ? WHERE id = ?",
                      (data['total_amount'] - data.get('paid_amount', 0), data['supplier_id']))

        conn.commit()
        purchase_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': purchase_id, 'purchase_number': purchase_number})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# Employees endpoints
@app.route('/api/employees', methods=['GET'])
def get_employees():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM employees ORDER BY created_at DESC")
    employees = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(employees)

@app.route('/api/employees', methods=['POST'])
def create_employee():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO employees (name, phone, email, role, salary, joining_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['name'], data['phone'], data.get('email'), data['role'],
              data.get('salary'), data.get('joining_date')))

        conn.commit()
        employee_id = cursor.lastrowid
        conn.close()

        return jsonify({'success': True, 'id': employee_id})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/employees/<int:employee_id>', methods=['PUT'])
def update_employee(employee_id):
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            UPDATE employees
            SET name=?, phone=?, email=?, role=?, salary=?, status=?
            WHERE id=?
        ''', (data['name'], data['phone'], data.get('email'), data['role'],
              data.get('salary'), data.get('status', 'Active'), employee_id))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/employees/<int:employee_id>', methods=['DELETE'])
def delete_employee(employee_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM employees WHERE id=?", (employee_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Attendance endpoints
@app.route('/api/attendance', methods=['GET'])
def get_attendance():
    conn = get_db()
    cursor = conn.cursor()

    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    cursor.execute("""
        SELECT e.id as employee_id, e.name, e.role,
               a.id as attendance_id, a.status, a.notes
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.employee_id AND a.date = ?
        WHERE e.status = 'Active'
        ORDER BY e.name
    """, (date,))

    attendance = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(attendance)

@app.route('/api/attendance', methods=['POST'])
def mark_attendance():
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT OR REPLACE INTO attendance (employee_id, date, status, notes)
            VALUES (?, ?, ?, ?)
        ''', (data['employee_id'], data['date'], data['status'], data.get('notes')))

        conn.commit()
        conn.close()

        return jsonify({'success': True})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 400

# Reports endpoints
@app.route('/api/reports/sales', methods=['GET'])
def sales_report():
    conn = get_db()
    cursor = conn.cursor()

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    if start_date and end_date:
        cursor.execute("""
            SELECT * FROM sales
            WHERE DATE(created_at) BETWEEN ? AND ?
            ORDER BY created_at DESC
        """, (start_date, end_date))
    else:
        cursor.execute("SELECT * FROM sales ORDER BY created_at DESC LIMIT 100")

    sales = [dict(row) for row in cursor.fetchall()]

    # Calculate totals
    total_sales = sum(s['total_amount'] for s in sales)
    total_orders = len(sales)

    conn.close()

    return jsonify({
        'sales': sales,
        'total_sales': total_sales,
        'total_orders': total_orders
    })

@app.route('/api/reports/inventory', methods=['GET'])
def inventory_report():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products ORDER BY stock ASC")
    products = [dict(row) for row in cursor.fetchall()]

    total_value = sum(p['stock'] * p['selling_price'] for p in products)
    low_stock_count = sum(1 for p in products if p['stock'] <= p['min_stock'])

    conn.close()

    return jsonify({
        'products': products,
        'total_value': total_value,
        'low_stock_count': low_stock_count
    })

@app.route('/api/reports/customers', methods=['GET'])
def customers_report():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM customers ORDER BY total_purchases DESC")
    customers = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(customers)

# Settings endpoints
@app.route('/api/change-password', methods=['POST'])
def change_password():
    data = request.json

    user_id = data.get('user_id')
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not all([user_id, old_password, new_password]):
        return jsonify({'success': False, 'message': 'All fields required'}), 400

    old_password_hash = hashlib.sha256(old_password.encode()).hexdigest()
    new_password_hash = hashlib.sha256(new_password.encode()).hexdigest()

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE id=? AND password=?", (user_id, old_password_hash))
    user = cursor.fetchone()

    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'Current password incorrect'}), 401

    cursor.execute("UPDATE users SET password=? WHERE id=?", (new_password_hash, user_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'message': 'Password changed successfully'})

@app.route('/api/login-activity', methods=['GET'])
def get_login_activity():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM login_activity ORDER BY login_time DESC LIMIT 50")
    activity = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(activity)

# Serve frontend
@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    init_db()
    print("=" * 60)
    print("KidsWear Pro POS System - Starting Server")
    print("=" * 60)
    print("\n✓ Database initialized")
    print("✓ Server running on: http://localhost:5000")
    print("\n📌 Default Login Credentials:")
    print("   Username: admin")
    print("   Password: admin123")
    print("\n" + "=" * 60)
    print("Press Ctrl+C to stop the server")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
