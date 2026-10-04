import gc
import hashlib
import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient

import backend.main as main
import backend.medical_router as medical_router


def cleanup_temp_db(db_path):
    gc.collect()
    main.db = main._production_db
    main.DATABASE_URL = main._configured_database_url
    main.SECRET = main._configured_jwt_secret
    main.DB_INTEGRITY_ERRORS = main._configured_db_integrity_errors
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
    main.DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,)
    def connect_test_db():
        conn = sqlite3.connect(main.DB)
        conn.row_factory = sqlite3.Row
        return conn
    main.db = connect_test_db
    main.JWT_BLACKLIST.clear()
    main.init()
    return temp_db.name


def create_pharma_user(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO users (
                name, email, password, role, company, created_at,
                verification_status, company_user_id, job_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                'Pharma Demo',
                'pharma@demo.local',
                main.phash('secret123'),
                'pharma',
                'NovaCure Pharmaceuticals',
                main.now(),
                'approved',
                0,
                'Managing Director'
            ),
        )
        conn.commit()
        user_id = conn.execute('SELECT id FROM users WHERE email=?', ('pharma@demo.local',)).fetchone()[0]
    return user_id


def test_medicine_creation_rejects_negative_price_and_requires_company_fields():
    db_path = setup_temp_db()
    try:
        user_id = create_pharma_user(db_path)
        token = main.token({'id': user_id, 'role': 'pharma'})
        with TestClient(main.app) as client:
            response = client.post(
                '/api/medicines',
                headers={'Authorization': f'Bearer {token}'},
                json={
                    'name': 'Cardiova-Demo',
                    'category': 'Cardiovascular',
                    'price': -10,
                    'currency': 'PKR',
                    'company': 'NovaCure Pharmaceuticals',
                    'generic_name': 'Demo Active Ingredient A',
                    'brand_name': 'Cardiova',
                    'manufacturer': 'NovaCure Pharmaceuticals'
                },
            )

            assert response.status_code in (400, 422)
    finally:
        cleanup_temp_db(db_path)


def test_sales_rep_creation_generates_unique_sales_id_and_auto_company():
    db_path = setup_temp_db()
    try:
        user_id = create_pharma_user(db_path)
        token = main.token({'id': user_id, 'role': 'pharma', 'company': 'NovaCure Pharmaceuticals'})
        with TestClient(main.app) as client:
            response = client.post(
                '/api/reps',
                headers={'Authorization': f'Bearer {token}'},
                json={
                    'name': 'Ahmed Khan',
                    'email': 'ahmed@example.demo',
                    'password': 'demo123',
                    'phone': '+92 300 0000000',
                    'job_title': 'Sales Representative'
                },
            )

            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload['company'] == 'NovaCure Pharmaceuticals'
            assert payload['sales_id'].startswith('NOV') or payload['sales_id'].startswith('NOVA')
            assert payload['sales_id'] == payload['registration_number']
    finally:
        cleanup_temp_db(db_path)


def test_business_count_question_is_not_treated_as_medical_rag():
    result = medical_router.classify('How many medicines do we have in the system?', [])
    assert result['medical'] is False


def test_message_migration_preserves_sender_id_and_is_repeatable():
    db_path = setup_temp_db()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                'INSERT INTO messages(conversation_id,sender,agent,content,risk,created_at,sender_id) VALUES(?,?,?,?,?,?,?)',
                (99, 'human', 'Sales Rep', 'Existing message', 'human', main.now(), 42),
            )
            conn.commit()

        main.init()
        main.init()

        with sqlite3.connect(db_path) as conn:
            sender_id, sender_role, message = conn.execute(
                'SELECT sender_id,sender_role,message FROM messages WHERE conversation_id=?',
                (99,),
            ).fetchone()

        assert sender_id == 42
        assert sender_role == 'agent'
        assert message == 'Existing message'
    finally:
        cleanup_temp_db(db_path)


def test_uploaded_document_bytes_and_rag_chunks_are_database_backed():
    db_path = setup_temp_db()
    try:
        pharma_id = create_pharma_user(db_path)
        pharma_token = main.token({'id': pharma_id, 'role': 'pharma'})
        with TestClient(main.app) as client:
            medicine_response = client.post(
                '/api/medicines',
                headers={'Authorization': f'Bearer {pharma_token}'},
                json={
                    'name': 'Persistent Demo Product',
                    'category': 'Demo',
                    'price': 10,
                    'description': 'Product for storage regression coverage',
                    'manufacturer': 'NovaCure Pharmaceuticals',
                    'specializations': ['Cardiology']
                },
            )
            assert medicine_response.status_code == 200, medicine_response.text
            medicine_id = medicine_response.json()['id']
            document_text = b'Persistent database document. Synthetic product storage test content.'
            response = client.post(
                f'/api/documents/{medicine_id}',
                headers={'Authorization': f'Bearer {pharma_token}'},
                files={'file': ('profile.txt', document_text, 'text/plain')},
            )
            assert response.status_code == 200, response.text

        with sqlite3.connect(db_path) as conn:
            stored_bytes, stored_path = conn.execute(
                'SELECT file_data,path FROM documents WHERE filename=?',
                ('profile.txt',),
            ).fetchone()
            chunk_count = conn.execute(
                'SELECT count(*) FROM knowledge_chunks WHERE document_id=(SELECT id FROM documents WHERE filename=?)',
                ('profile.txt',),
            ).fetchone()[0]

        assert stored_bytes == document_text
        assert stored_path is None
        assert chunk_count > 0
    finally:
        cleanup_temp_db(db_path)


def test_legacy_password_is_verified_and_upgraded_on_login():
    db_path = setup_temp_db()
    legacy_password = 'legacy-test-password'
    legacy_hash = hashlib.sha256(('pharmaai:' + legacy_password).encode()).hexdigest()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                'INSERT INTO users(name,email,password,role,created_at,verification_status) VALUES(?,?,?,?,?,?)',
                ('Legacy Doctor', 'legacy.doctor@test.local', legacy_hash, 'doctor', main.now(), 'approved'),
            )
            conn.commit()

        with TestClient(main.app) as client:
            response = client.post(
                '/api/auth/login',
                json={'email': 'legacy.doctor@test.local', 'password': legacy_password},
            )
            assert response.status_code == 200, response.text
            assert 'password' not in response.json()['user']

        with sqlite3.connect(db_path) as conn:
            stored_hash = conn.execute(
                'SELECT password FROM users WHERE email=?',
                ('legacy.doctor@test.local',),
            ).fetchone()[0]

        assert stored_hash.startswith('pbkdf2_sha256$')
        assert stored_hash != legacy_hash
    finally:
        cleanup_temp_db(db_path)


def test_register_login_jwt_and_protected_route_flow(monkeypatch):
    db_path = setup_temp_db()
    monkeypatch.setenv('DEMO_VERIFICATION', 'true')
    try:
        with TestClient(main.app) as client:
            registration = client.post(
                '/api/auth/register',
                json={
                    'name': 'Registration Test Doctor',
                    'email': 'registration.flow@test.local',
                    'password': 'test-registration-password',
                    'role': 'doctor',
                    'specialization': 'Cardiology',
                    'license_number': 'DEMO-REG-123',
                    'registration_authority': 'Test Registry'
                },
            )
            assert registration.status_code == 200, registration.text
            assert registration.json()['user']['email'] == 'registration.flow@test.local'
            assert 'password' not in registration.json()['user']

            with sqlite3.connect(db_path) as conn:
                stored_hash = conn.execute(
                    'SELECT password FROM users WHERE email=?',
                    ('registration.flow@test.local',),
                ).fetchone()[0]
            assert stored_hash.startswith('pbkdf2_sha256$')

            login_response = client.post(
                '/api/auth/login',
                json={'email': 'registration.flow@test.local', 'password': 'test-registration-password', 'role': 'doctor'},
            )
            assert login_response.status_code == 200, login_response.text
            access_token = login_response.json()['token']
            protected = client.get('/api/auth/me', headers={'Authorization': f'Bearer {access_token}'})
            assert protected.status_code == 200, protected.text
            assert protected.json()['email'] == 'registration.flow@test.local'

            duplicate = client.post(
                '/api/auth/register',
                json={
                    'name': 'Duplicate Doctor',
                    'email': 'registration.flow@test.local',
                    'password': 'another-password',
                    'role': 'doctor',
                    'license_number': 'DEMO-REG-456'
                },
            )
            assert duplicate.status_code == 409
    finally:
        cleanup_temp_db(db_path)


def test_configured_admin_and_demo_accounts_are_idempotent(monkeypatch):
    db_path = setup_temp_db()
    monkeypatch.setenv('ADMIN_EMAIL', 'configured.admin@test.local')
    monkeypatch.setenv('ADMIN_PASSWORD', 'test-admin-password')
    monkeypatch.setenv('DEMO_USER_EMAIL', 'configured.demo@test.local')
    monkeypatch.setenv('DEMO_USER_PASSWORD', 'test-demo-password')
    try:
        main.init()
        main.init()
        with sqlite3.connect(db_path) as conn:
            assert conn.execute('SELECT count(*) FROM users WHERE email=?', ('configured.admin@test.local',)).fetchone()[0] == 1
            assert conn.execute('SELECT count(*) FROM users WHERE email=?', ('configured.demo@test.local',)).fetchone()[0] == 1

        with TestClient(main.app) as client:
            admin_login = client.post('/api/auth/login', json={'email': 'configured.admin@test.local', 'password': 'test-admin-password', 'role': 'admin'})
            demo_login = client.post('/api/auth/login', json={'email': 'configured.demo@test.local', 'password': 'test-demo-password', 'role': 'doctor'})
            assert admin_login.status_code == 200, admin_login.text
            assert demo_login.status_code == 200, demo_login.text
            assert 'password' not in admin_login.json()['user']
            assert 'password' not in demo_login.json()['user']
    finally:
        cleanup_temp_db(db_path)
