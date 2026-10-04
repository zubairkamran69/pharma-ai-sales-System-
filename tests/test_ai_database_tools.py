"""
Regression tests for the two production failures fixed in this change.

1. Platform Owner -> Verification Users returned HTTP 500 for
   `rows(connection.execute(...))`, because PostgresCompatCursor did not
   implement the iteration protocol. Starlette builds that 500 outside the CORS
   middleware, so the browser could not read the response and the frontend
   reported "Cannot reach the Render API".
2. The AI supervisor answered "I can't help with that" for every request about
   stored records, because the database tool layer was never reached from the
   chat router.

These tests never touch the network and never touch the production database.
"""
import os
import sqlite3

from fastapi.testclient import TestClient

import backend.main as main


class _FakeDictCursor(list):
    """Minimal stand-in for a psycopg2 DictCursor result set."""

    description = None
    rowcount = -1


def test_postgres_compat_cursor_supports_sqlite_style_iteration():
    """
    The whole codebase reads rows with `rows(c.execute(sql, params))`.

    Special methods are looked up on the type and never through __getattr__, so
    the wrapper has to declare them. Without __iter__ this raises
    "TypeError: 'PostgresCompatCursor' object is not iterable" against psycopg2
    while the SQLite test database keeps working - which is exactly why the
    platform-owner verification page failed only in production.
    """
    inner = _FakeDictCursor([{'id': 1, 'name': 'first'}, {'id': 2, 'name': 'second'}])
    cursor = main.PostgresCompatCursor(inner, lastrowid=2)

    assert [row['id'] for row in cursor] == [1, 2]
    assert list(cursor) == [{'id': 1, 'name': 'first'}, {'id': 2, 'name': 'second'}]
    assert len(cursor) == 2
    assert cursor[0]['name'] == 'first'
    assert main.rows(cursor) == [{'id': 1, 'name': 'first'}, {'id': 2, 'name': 'second'}]
    assert cursor.lastrowid == 2
    assert cursor.rowcount == -1


def test_postgres_compat_connection_exposes_rollback():
    """
    psycopg2 aborts the whole transaction after a failed statement, so a tool
    that fails must be able to clear it before the next query runs.
    """
    assert hasattr(main.PostgresCompatConnection, 'rollback')


def _setup_temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / 'ai_tools.db')
    monkeypatch.setattr(main, 'DATABASE_URL', 'postgresql://isolated-test.invalid/test')
    monkeypatch.setattr(main, 'SECRET', 'isolated-test-secret-value-at-least-32-chars')

    def connect_test_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(main, 'db', connect_test_db)
    monkeypatch.setattr(main, 'DB_INTEGRITY_ERRORS', (sqlite3.IntegrityError,))
    monkeypatch.setenv('ADMIN_EMAIL', '')
    monkeypatch.setenv('ADMIN_PASSWORD', '')
    monkeypatch.setenv('DEMO_USER_EMAIL', '')
    monkeypatch.setenv('DEMO_USER_PASSWORD', '')
    main.JWT_BLACKLIST.clear()
    main.init()
    return db_path


def _add_user(db_path, email, role, **extra):
    fields = {
        'name': email.split('@')[0],
        'email': email,
        'password': main.phash('tool-test-password'),
        'role': role,
        'specialization': 'Cardiology',
        'company': '',
        'created_at': main.now(),
        'verification_status': 'approved',
    }
    fields.update(extra)
    columns = ', '.join(fields)
    placeholders = ', '.join('?' for _ in fields)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            f'INSERT INTO users({columns}) VALUES({placeholders})',
            tuple(fields.values()),
        )
        conn.commit()
        return cursor.lastrowid


def _add_medicine(db_path, name, owner_user_id, company, **extra):
    fields = {
        'name': name,
        'category': 'Cardiology',
        'price': 100,
        'description': 'tool test product',
        'specializations': '["Cardiology"]',
        'stock': 10,
        'status': 'Active',
        'sales': 0,
        'created_at': main.now(),
        'owner_user_id': owner_user_id,
        'company': company,
        'manufacturer': company,
    }
    fields.update(extra)
    columns = ', '.join(fields)
    placeholders = ', '.join('?' for _ in fields)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f'INSERT INTO medicines({columns}) VALUES({placeholders})',
            tuple(fields.values()),
        )
        conn.commit()


def _user(db_path, user_id):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone())


def test_list_products_is_scoped_to_the_callers_company(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    alpha = _add_user(db_path, 'alpha@tools.local', 'pharma', company='Alpha Pharma')
    beta = _add_user(db_path, 'beta@tools.local', 'pharma', company='Beta Pharma')
    _add_medicine(db_path, 'Alpha Product 5', alpha, 'Alpha Pharma')
    _add_medicine(db_path, 'Beta Product 7', beta, 'Beta Pharma')

    c = main.db()
    try:
        result = main.run_ai_tool(c, _user(db_path, alpha), 'list_products', {})
    finally:
        c.close()

    assert result['scope'] == 'company_portfolio'
    assert [p['name'] for p in result['products']] == ['Alpha Product 5']
    assert 'Beta Product 7' not in str(result)


def test_list_products_search_filter_is_applied(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    owner = _add_user(db_path, 'search@tools.local', 'pharma', company='Search Pharma')
    _add_medicine(db_path, 'Neurovia 50', owner, 'Search Pharma', brand_name='Neurovia')
    _add_medicine(db_path, 'Cardiovex 10', owner, 'Search Pharma', brand_name='Cardiovex')

    c = main.db()
    try:
        result = main.run_ai_tool(c, _user(db_path, owner), 'list_products', {'search': 'cardiovex'})
    finally:
        c.close()

    assert [p['name'] for p in result['products']] == ['Cardiovex 10']


def test_list_products_for_owner_sees_every_company(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    owner = _add_user(db_path, 'owner@tools.local', 'admin', company='PharmaAI Platform')
    company = _add_user(db_path, 'gamma@tools.local', 'pharma', company='Gamma Pharma')
    _add_medicine(db_path, 'Gamma Product', company, 'Gamma Pharma')

    c = main.db()
    try:
        result = main.run_ai_tool(c, _user(db_path, owner), 'list_products', {})
    finally:
        c.close()

    assert result['scope'] == 'platform'
    assert [p['name'] for p in result['products']] == ['Gamma Product']


def test_list_doctors_only_returns_verified_network_to_companies(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    company = _add_user(db_path, 'rep@tools.local', 'pharma', company='Delta Pharma')
    _add_user(db_path, 'verified@tools.local', 'doctor', verification_status='approved')
    _add_user(db_path, 'pending@tools.local', 'doctor', verification_status='pending')

    c = main.db()
    try:
        company_view = main.run_ai_tool(c, _user(db_path, company), 'list_doctors', {})
        owner = _add_user(db_path, 'owner2@tools.local', 'admin', company='PharmaAI Platform')
        owner_view = main.run_ai_tool(c, _user(db_path, owner), 'list_doctors', {})
    finally:
        c.close()

    assert [d['email'] for d in company_view['doctors']] == ['verified@tools.local']
    assert company_view['scope'] == 'verified_network'
    assert {d['email'] for d in owner_view['doctors']} == {'verified@tools.local', 'pending@tools.local'}


def test_doctor_only_sees_their_own_record(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    doctor = _add_user(db_path, 'doc@tools.local', 'doctor', verification_status='approved')
    _add_user(db_path, 'other@tools.local', 'doctor', verification_status='approved')

    c = main.db()
    try:
        result = main.run_ai_tool(c, _user(db_path, doctor), 'list_doctors', {})
    finally:
        c.close()

    assert result['scope'] == 'own_record'
    assert [d['email'] for d in result['doctors']] == ['doc@tools.local']


def test_verification_queue_and_overview_are_admin_only(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    doctor = _add_user(db_path, 'doc2@tools.local', 'doctor', verification_status='pending')
    owner = _add_user(db_path, 'owner3@tools.local', 'admin', company='PharmaAI Platform')

    c = main.db()
    try:
        doctor_queue = main.run_ai_tool(c, _user(db_path, doctor), 'list_users_by_verification', {})
        owner_queue = main.run_ai_tool(c, _user(db_path, owner), 'list_users_by_verification', {})
        doctor_overview = main.run_ai_tool(c, _user(db_path, doctor), 'get_platform_overview', {})
        owner_overview = main.run_ai_tool(c, _user(db_path, owner), 'get_platform_overview', {})
    finally:
        c.close()

    assert 'error' in doctor_queue
    assert 'error' in doctor_overview
    assert [u['email'] for u in owner_queue['users']] == ['doc2@tools.local']
    assert owner_overview['doctors'] == 1
    assert owner_overview['pending_verifications'] == 1


def test_get_product_details_refuses_another_companys_product(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    alpha = _add_user(db_path, 'alpha2@tools.local', 'pharma', company='Alpha 2')
    beta = _add_user(db_path, 'beta2@tools.local', 'pharma', company='Beta 2')
    _add_medicine(db_path, 'Beta Secret', beta, 'Beta 2')

    c = main.db()
    try:
        allowed = main.run_ai_tool(c, _user(db_path, alpha), 'get_product_details', {'name': 'Beta Secret'})
    finally:
        c.close()

    assert 'error' in allowed
    assert 'another company' in allowed['error'].lower()


def test_platform_record_requests_are_not_treated_as_medicine_questions():
    for message in (
        'show my products',
        'show my product',
        'show medicines',
        'show company medicines',
        'list my medicines',
        'list doctors',
        'which doctors are registered?',
        'what products do I have?',
        'what medicines does my company have?',
        'show the verification queue',
        'Tell me about all the medicines we have in the system.',
    ):
        assert main.platform_record_request(message), message


def test_clinical_medicine_questions_stay_on_the_rag_route():
    for message in (
        'what are the side effects of Cardiovex 10',
        'what is the dose of Cardiovex 10',
        'composition of Aspirin',
        'list the ingredients in my medicines',
        'storage instructions for RespiraCalm 5',
    ):
        assert not main.platform_record_request(message), message


def test_chat_router_uses_the_database_tools(tmp_path, monkeypatch):
    """
    The tool layer existed but was never called from agent_answer, so every
    record question fell through to the general chat model. This asserts the
    wiring itself, with the provider stubbed out.
    """
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    doctor = _add_user(db_path, 'router@tools.local', 'doctor', verification_status='approved')
    _add_medicine(db_path, 'Router Product', None, 'Router Pharma')

    seen = {}

    def fake_session(c, u, msg, force_tools=False):
        seen['user_id'] = u['id']
        seen['force_tools'] = force_tools
        seen['message'] = msg
        return True, 'Router Product is in the catalogue.', [
            {'tool': 'list_products', 'arguments': {}, 'summary': '1 products: Router Product', 'ok': True}
        ], 'test:model'

    monkeypatch.setattr(main, 'run_ai_tool_session', fake_session)

    c = main.db()
    try:
        answer = main.agent_answer(_user(db_path, doctor), 'show my products')
    finally:
        c.close()

    assert answer['route'] == 'database-tools'
    assert 'Router Product' in answer['message']
    assert answer['tools'][0]['tool'] == 'list_products'
    assert seen['user_id'] == doctor
    assert seen['force_tools'] is True


def test_clinical_question_does_not_open_a_tool_session(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    doctor = _add_user(db_path, 'clinical@tools.local', 'doctor', verification_status='approved')

    def unexpected_session(*_args, **_kwargs):
        raise AssertionError('the RAG route must not open a tool session')

    monkeypatch.setattr(main, 'run_ai_tool_session', unexpected_session)

    c = main.db()
    try:
        # No documents are indexed, so the approved-knowledge answer is used.
        answer = main.agent_answer(_user(db_path, doctor), 'what are the side effects of Cardiovex 10')
    finally:
        c.close()

    assert answer['agent'] == 'Product Knowledge + RAG Agent'


def test_owner_login_and_admin_users_listing(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    _add_user(db_path, 'owner.flow@tools.local', 'admin', company='PharmaAI Platform')
    origin = 'https://pharma-ai-sales-system-frontend.vercel.app'

    with TestClient(main.app) as client:
        registration = client.post('/api/auth/register', json={
            'name': 'Pending Doctor',
            'email': 'pending.flow@tools.local',
            'password': 'pending-doctor-password',
            'role': 'doctor',
            'specialization': 'Cardiology',
            'license_number': 'TOOLS-PMDC-2',
            'registration_authority': 'PM&DC',
        })
        assert registration.status_code == 200, registration.text
        doctor_id = registration.json()['user']['id']

        login = client.post('/api/auth/login', json={
            'email': 'owner.flow@tools.local', 'password': 'tool-test-password', 'role': 'admin',
        })
        assert login.status_code == 200, login.text
        assert 'password' not in login.json()['user']

        headers = {'Authorization': f"Bearer {login.json()['token']}", 'Origin': origin}
        users = client.get('/api/admin/users', headers=headers)
        assert users.status_code == 200, users.text
        assert users.headers['access-control-allow-origin'] == origin
        pending = next(user for user in users.json() if user['id'] == doctor_id)
        assert pending['verification_status'] == 'pending'
        assert 'password' not in pending

        approved = client.patch(
            f'/api/admin/users/{doctor_id}/verification',
            headers=headers,
            json={'decision': 'approved', 'note': 'verified in test'},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json() == {'ok': True, 'status': 'approved'}

        with sqlite3.connect(db_path) as conn:
            status = conn.execute(
                'SELECT verification_status FROM users WHERE id=?', (doctor_id,)
            ).fetchone()[0]
        assert status == 'approved'


def test_admin_users_requires_the_owner_role(tmp_path, monkeypatch):
    db_path = _setup_temp_db(tmp_path, monkeypatch)
    _add_user(db_path, 'plain.doc@tools.local', 'doctor', verification_status='approved')

    with TestClient(main.app) as client:
        login = client.post('/api/auth/login', json={
            'email': 'plain.doc@tools.local', 'password': 'tool-test-password',
        })
        assert login.status_code == 200, login.text
        headers = {'Authorization': f"Bearer {login.json()['token']}"}
        denied = client.get('/api/admin/users', headers=headers)
        assert denied.status_code == 403, denied.text
        anonymous = client.get('/api/admin/users')
        assert anonymous.status_code == 401, anonymous.text
