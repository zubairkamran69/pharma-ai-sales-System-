import sqlite3

from fastapi.testclient import TestClient

import backend.main as main


def setup_temp_db():
    import os
    import tempfile
    import gc

    temp_db = tempfile.NamedTemporaryFile(prefix='pharmaai_chat_', suffix='.db', delete=False)
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


def cleanup_temp_db(db_path):
    import gc
    import os

    main.db = main._production_db
    main.DATABASE_URL = main._configured_database_url
    main.SECRET = main._configured_jwt_secret
    main.DB_INTEGRITY_ERRORS = main._configured_db_integrity_errors
    try:
        os.unlink(db_path)
    except FileNotFoundError:
        pass
    except PermissionError:
        pass
    gc.collect()


def seed_company_chat_data(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
            ('Doctor A', 'doctor.a@test.local', main.phash('secret'), 'doctor', 'Demo', main.now(), 'approved', None),
        )
        conn.execute(
            "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
            ('Doctor B', 'doctor.b@test.local', main.phash('secret'), 'doctor', 'Demo', main.now(), 'approved', None),
        )
        for company_name, company_email, company_id in [
            ('Company A', 'company.a@test.local', 101),
            ('Company B', 'company.b@test.local', 102),
            ('Company C', 'company.c@test.local', 103),
        ]:
            conn.execute(
                "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
                (company_name, company_email, main.phash('secret'), 'pharma', company_name, main.now(), 'approved', company_id),
            )
        conn.execute(
            "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
            ('Rep A', 'rep.a@test.local', main.phash('secret'), 'sales_rep', 'Company A', main.now(), 'approved', 101),
        )
        conn.execute(
            "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
            ('Rep B', 'rep.b@test.local', main.phash('secret'), 'sales_rep', 'Company B', main.now(), 'approved', 102),
        )
        conn.execute(
            "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
            ('Rep C', 'rep.c@test.local', main.phash('secret'), 'sales_rep', 'Company C', main.now(), 'approved', 103),
        )
        conn.execute(
            "INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,sales_representative_id,company_user_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 'doctor', 'human', 1, 101, 4, 101, 'open', main.now()),
        )
        conn.execute(
            "INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,sales_representative_id,company_user_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 'doctor', 'human', 1, 102, 5, 102, 'open', main.now()),
        )
        conn.execute(
            "INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,sales_representative_id,company_user_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 'doctor', 'human', 1, 103, 6, 103, 'open', main.now()),
        )
        conn.commit()


def test_company_chat_access_matrix_is_enforced():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        with TestClient(main.app) as client:
            doctor_token = main.token({'id': 1, 'role': 'doctor'})
            company_a_token = main.token({'id': 3, 'role': 'pharma', 'company_user_id': 101})
            rep_a_token = main.token({'id': 4, 'role': 'sales_rep', 'company_user_id': 101})
            doctor_b_token = main.token({'id': 2, 'role': 'doctor'})

            doctor_list = client.get('/api/conversations', headers={'Authorization': f'Bearer {doctor_token}'})
            assert doctor_list.status_code == 200, doctor_list.text
            assert len(doctor_list.json()) == 3

            company_a_list = client.get('/api/conversations', headers={'Authorization': f'Bearer {company_a_token}'})
            assert company_a_list.status_code == 200, company_a_list.text
            company_ids = {item['company_id'] for item in company_a_list.json()}
            assert company_ids == {101}

            rep_a_access = client.get('/api/conversations/2', headers={'Authorization': f'Bearer {rep_a_token}'})
            assert rep_a_access.status_code == 403, rep_a_access.text

            doctor_b_access = client.get('/api/conversations/1', headers={'Authorization': f'Bearer {doctor_b_token}'})
            assert doctor_b_access.status_code == 403, doctor_b_access.text

            create_response = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 101},
            )
            assert create_response.status_code == 200, create_response.text
            assert create_response.json()['company_id'] == 101
    finally:
        cleanup_temp_db(db_path)
