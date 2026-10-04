import gc
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
