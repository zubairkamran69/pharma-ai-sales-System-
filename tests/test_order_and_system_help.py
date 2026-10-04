import gc
import os
import sqlite3
import tempfile

from fastapi.testclient import TestClient

import backend.main as main


def cleanup_temp_db(db_path):
    gc.collect()
    main.db = main._production_db
    main.DATABASE_URL = main._configured_database_url
    main.SECRET = main._configured_jwt_secret
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass
    except PermissionError:
        # SQLite on Windows can keep a temp DB file locked briefly even after
        # the connection is closed; the test still has valid coverage without
        # failing cleanup on that OS-specific artifact.
        pass


def setup_temp_db():
    temp_db = tempfile.NamedTemporaryFile(prefix='pharmaai_', suffix='.db', delete=False)
    temp_db.close()
    main.DB = temp_db.name
    main.DATABASE_URL = 'postgresql://isolated-test.invalid/test'
    main.SECRET = 'isolated-test-secret-value-at-least-32-chars'
    def connect_test_db():
        conn = sqlite3.connect(main.DB)
        conn.row_factory = sqlite3.Row
        return conn
    main.db = connect_test_db
    main.JWT_BLACKLIST.clear()
    main.init()
    return temp_db.name


def test_doctor_can_create_order_and_backend_resolves_company_and_rep():
    db_path = setup_temp_db()
    try:
        with TestClient(main.app) as client:
            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            token = doctor['token']
            medicine = client.get('/api/medicines', headers={'Authorization': f'Bearer {token}'})
            medicine_id = medicine.json()[0]['id']

            response = client.post(
                '/api/orders',
                headers={'Authorization': f'Bearer {token}'},
                json={'medicine_id': medicine_id, 'quantity': 5, 'requested_date': '2026-10-20', 'notes': 'Please confirm with representative'}
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert 'order_no' in payload
            assert payload['status'] in {'Pending', 'Assigned', 'Under Review'}
            assert payload['company_id'] is not None
            if payload.get('sales_rep_id') is not None:
                with sqlite3.connect(db_path) as conn:
                    rep = conn.execute('SELECT id, company_user_id FROM users WHERE id=?', (payload['sales_rep_id'],)).fetchone()
                    assert rep is not None
            with sqlite3.connect(db_path) as conn:
                order_row = conn.execute('SELECT * FROM orders WHERE order_no=?', (payload['order_no'],)).fetchone()
                assert order_row is not None
    finally:
        cleanup_temp_db(db_path)


def test_system_help_role_response_for_doctor_without_medicine_management_permission():
    db_path = setup_temp_db()
    try:
        with TestClient(main.app) as client:
            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            token = doctor['token']

            response = client.post(
                '/api/chat',
                headers={'Authorization': f'Bearer {token}'},
                json={'message': 'How do I upload a medicine?'}
            )

            assert response.status_code == 200, response.text
            text = response.json()['message'].lower()
            assert 'not currently available' in text or 'cannot create or modify company medicines' in text

            with sqlite3.connect(db_path) as conn:
                conn.execute('DELETE FROM users WHERE email=?', ('doctor@pharmaai.local',))
                conn.commit()
    finally:
        cleanup_temp_db(db_path)


def test_broad_medicine_question_uses_general_answer_when_pharmaai_data_is_incomplete():
    db_path = setup_temp_db()
    try:
        with TestClient(main.app) as client:
            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            token = doctor['token']

            response = client.post(
                '/api/chat',
                headers={'Authorization': f'Bearer {token}'},
                json={'message': 'Tell me about all the medicines we have in the system.'}
            )

            assert response.status_code == 200, response.text
            text = response.json()['message']
            lower = text.lower()
            assert 'general ai information' in lower or 'not pharmaai verified' in lower
            assert 'pharmaai knowledge base' in lower or 'pharmaai-verified' in lower or 'pharmaai verified' in lower
            assert 'specify a medicine name' in lower or 'tell me the medicine name' in lower
            assert 'i do not have this information' not in lower
            assert 'approved knowledge base does not contain' not in lower
    finally:
        cleanup_temp_db(db_path)


def test_pharma_company_can_manage_order_status_and_doctor_sees_updates():
    db_path = setup_temp_db()
    try:
        with TestClient(main.app) as client:
            pharma_email = 'pharma.orderflow@demo.local'
            pharma_password = 'pharma123'
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO users (
                        name, email, password, role, company, created_at,
                        verification_status, company_user_id, job_title
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        'NovaCure Pharma Ops',
                        pharma_email,
                        main.phash(pharma_password),
                        'pharma',
                        'NovaCure Pharmaceuticals',
                        main.now(),
                        'approved',
                        0,
                        'Operations Lead'
                    ),
                )
                conn.commit()

            pharma = client.post('/api/auth/login', json={'email': pharma_email, 'password': pharma_password}).json()
            pharma_token = pharma['token']
            medicine = client.post(
                '/api/medicines',
                headers={'Authorization': f'Bearer {pharma_token}'},
                json={
                    'name': 'NovaCure Order Flow',
                    'category': 'Cardiovascular',
                    'price': 240.00,
                    'currency': 'PKR',
                    'description': 'Order workflow validation medicine',
                    'generic_name': 'Workflow Active Ingredient',
                    'brand_name': 'NovaFlow',
                    'therapeutic_area': 'Cardiology',
                    'dosage_form': 'Tablet',
                    'strength': '500 mg',
                    'manufacturer': 'NovaCure Pharmaceuticals',
                    'pack_size': '30 tablets',
                    'stock': 50,
                    'availability_status': 'In Stock',
                    'specializations': ['Cardiology'],
                    'composition': 'Workflow ingredient',
                    'indications': 'Cardiology workflow',
                    'contraindications': 'None in test',
                    'warnings': 'Test-only medicine',
                    'storage_information': 'Store below 25C',
                    'prescription_status': 'Prescription Required',
                    'status': 'Active'
                }
            ).json()

            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            doctor_token = doctor['token']

            order = client.post(
                '/api/orders',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'medicine_id': medicine['id'], 'quantity': 2, 'requested_date': '2026-10-08', 'notes': 'Please confirm'}
            )
            order_payload = order.json()
            assert order_payload['status'] == 'Pending', order_payload
            order_id = client.get('/api/orders', headers={'Authorization': f'Bearer {doctor_token}'}).json()[0]['id']

            company_orders = client.get('/api/orders', headers={'Authorization': f'Bearer {pharma_token}'}).json()
            company_order = next(item for item in company_orders if item['id'] == order_id)
            assert company_order['status'] == 'Pending'

            update = client.patch(
                f'/api/orders/{order_id}/status',
                headers={'Authorization': f'Bearer {pharma_token}'},
                json={'status': 'Under Review', 'note': 'Reviewing team has reviewed'}
            )
            assert update.status_code == 200, update.text
            assert update.json()['status'] == 'Under Review'

            for next_status in ['Confirmed', 'Processing', 'Dispatched', 'Delivered']:
                response = client.patch(
                    f'/api/orders/{order_id}/status',
                    headers={'Authorization': f'Bearer {pharma_token}'},
                    json={'status': next_status, 'note': f'Order moved to {next_status}'}
                )
                assert response.status_code == 200, response.text
                order_after = client.get('/api/orders/' + str(order_id), headers={'Authorization': f'Bearer {doctor_token}'}).json()['order']
                assert order_after['status'] == next_status, order_after

            invalid = client.patch(
                f'/api/orders/{order_id}/status',
                headers={'Authorization': f'Bearer {pharma_token}'},
                json={'status': 'Pending', 'note': 'bad transition'}
            )
            assert invalid.status_code == 400, invalid.text

            doctor_after = client.get('/api/orders', headers={'Authorization': f'Bearer {doctor_token}'}).json()[0]
            assert doctor_after['status'] == 'Delivered'

            timeline = client.get('/api/orders/' + str(order_id), headers={'Authorization': f'Bearer {doctor_token}'}).json()['timeline']
            assert any(step.get('new_status') == 'Delivered' for step in timeline)
    finally:
        cleanup_temp_db(db_path)


def test_private_human_chats_are_company_scoped_and_hidden_from_admin():
    db_path = setup_temp_db()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Zenora Pharma', 'zenora@demo.local', main.phash('zenora123'), 'pharma', 'Zenora Pharma', main.now(), 'approved', 0, 'Commercial Lead')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Abeel Rep', 'abeel@demo.local', main.phash('abeel123'), 'sales_rep', 'Zenora Pharma', main.now(), 'approved', 1, 'Regional Sales Rep')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('NovaPeak Pharma', 'novapeak@demo.local', main.phash('novapeak123'), 'pharma', 'NovaPeak Pharma', main.now(), 'approved', 0, 'Commercial Lead')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Raza Rep', 'raza@demo.local', main.phash('raza123'), 'sales_rep', 'NovaPeak Pharma', main.now(), 'approved', 3, 'Account Manager')
            )
            conn.execute(
                'INSERT INTO medicines(name, category, price, description, stock, status, created_at, owner_user_id, company) VALUES (?,?,?,?,?,?,?, ?,?)',
                ('Zenora Cardio Plus', 'Cardiovascular', 250.0, 'Company A medicine used for access tests', 25, 'Active', main.now(), 1, 'Zenora Pharma')
            )
            conn.execute(
                'INSERT INTO medicines(name, category, price, description, stock, status, created_at, owner_user_id, company) VALUES (?,?,?,?,?,?,?, ?,?)',
                ('NovaPeak Cardio Prime', 'Cardiovascular', 300.0, 'Company B medicine used for access tests', 12, 'Active', main.now(), 3, 'NovaPeak Pharma')
            )
            conn.commit()

        with TestClient(main.app) as client:
            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            doctor_token = doctor['token']
            medicine_a = client.get('/api/medicines', headers={'Authorization': f'Bearer {doctor_token}'}).json()
            medicine_a_id = next(item['id'] for item in medicine_a if item['company'] == 'Zenora Pharma')
            conv = client.post(f'/api/contact-rep/{medicine_a_id}', headers={'Authorization': f'Bearer {doctor_token}'})
            assert conv.status_code == 200, conv.text
            cid = conv.json()['conversation_id']

            rep_a = client.post('/api/auth/login', json={'email': 'abeel@demo.local', 'password': 'abeel123'}).json()
            rep_a_token = rep_a['token']
            rep_a_list = client.get('/api/human-conversations', headers={'Authorization': f'Bearer {rep_a_token}'})
            assert rep_a_list.status_code == 200, rep_a_list.text
            asserting_ids = {item['id'] for item in rep_a_list.json()}
            assert cid in asserting_ids

            rep_b = client.post('/api/auth/login', json={'email': 'raza@demo.local', 'password': 'raza123'}).json()
            rep_b_token = rep_b['token']
            rep_b_blocked = client.get(f'/api/human-conversations/{cid}', headers={'Authorization': f'Bearer {rep_b_token}'})
            assert rep_b_blocked.status_code == 403, rep_b_blocked.text

            admin = client.post('/api/auth/login', json={'email': 'admin@pharmaai.local', 'password': 'admin123'}).json()
            admin_token = admin['token']
            admin_get = client.get(f'/api/human-conversations/{cid}', headers={'Authorization': f'Bearer {admin_token}'})
            assert admin_get.status_code == 403, admin_get.text
            admin_list = client.get('/api/human-conversations', headers={'Authorization': f'Bearer {admin_token}'})
            assert admin_list.status_code == 403, admin_list.text
    finally:
        cleanup_temp_db(db_path)


def test_company_isolated_human_chats_reject_cross_company_access():
    db_path = setup_temp_db()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Alpha Pharma', 'alpha@demo.local', main.phash('alpha123'), 'pharma', 'Alpha Pharma', main.now(), 'approved', 0, 'Commercial Lead')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Alpha Rep', 'alpha.rep@demo.local', main.phash('alphaRep123'), 'sales_rep', 'Alpha Pharma', main.now(), 'approved', 1, 'Representative')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Beta Pharma', 'beta@demo.local', main.phash('beta123'), 'pharma', 'Beta Pharma', main.now(), 'approved', 0, 'Commercial Lead')
            )
            conn.execute(
                'INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id,job_title) VALUES (?,?,?,?,?,?,?,?,?)',
                ('Beta Rep', 'beta.rep@demo.local', main.phash('betaRep123'), 'sales_rep', 'Beta Pharma', main.now(), 'approved', 3, 'Representative')
            )
            conn.execute(
                'INSERT INTO medicines(name, category, price, description, stock, status, created_at, owner_user_id, company) VALUES (?,?,?,?,?,?,?, ?,?)',
                ('Alpha Cardio', 'Cardiovascular', 220.0, 'Alpha medicine for isolation test', 30, 'Active', main.now(), 1, 'Alpha Pharma')
            )
            conn.commit()

        with TestClient(main.app) as client:
            doctor = client.post('/api/auth/login', json={'email': 'doctor@pharmaai.local', 'password': 'doctor123'}).json()
            doctor_token = doctor['token']
            medicine_id = next(item['id'] for item in client.get('/api/medicines', headers={'Authorization': f'Bearer {doctor_token}'}).json() if item['company'] == 'Alpha Pharma')
            conv = client.post(f'/api/contact-rep/{medicine_id}', headers={'Authorization': f'Bearer {doctor_token}'})
            assert conv.status_code == 200, conv.text
            cid = conv.json()['conversation_id']

            other_company = client.post('/api/auth/login', json={'email': 'beta@demo.local', 'password': 'beta123'}).json()
            other_company_token = other_company['token']
            blocked_company = client.get(f'/api/human-conversations/{cid}', headers={'Authorization': f'Bearer {other_company_token}'})
            assert blocked_company.status_code == 403, blocked_company.text

            beta_rep = client.post('/api/auth/login', json={'email': 'beta.rep@demo.local', 'password': 'betaRep123'}).json()
            beta_rep_token = beta_rep['token']
            blocked_rep = client.get(f'/api/human-conversations/{cid}', headers={'Authorization': f'Bearer {beta_rep_token}'})
            assert blocked_rep.status_code == 403, blocked_rep.text

            owner = client.post('/api/auth/login', json={'email': 'owner@pharmaai.local', 'password': 'owner123'}).json()
            owner_token = owner['token']
            blocked_owner = client.get(f'/api/human-conversations/{cid}', headers={'Authorization': f'Bearer {owner_token}'})
            assert blocked_owner.status_code == 403, blocked_owner.text
    finally:
        cleanup_temp_db(db_path)
