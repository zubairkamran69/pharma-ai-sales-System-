import sqlite3
from concurrent.futures import ThreadPoolExecutor

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
            (1, 'doctor', 'human', 1, 101, 6, 101, 'open', main.now()),
        )
        conn.execute(
            "INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,sales_representative_id,company_user_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 'doctor', 'human', 1, 102, 7, 102, 'open', main.now()),
        )
        conn.execute(
            "INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,sales_representative_id,company_user_id,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (1, 'doctor', 'human', 1, 103, 8, 103, 'open', main.now()),
        )
        conn.commit()


def test_company_chat_access_matrix_is_enforced():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        with TestClient(main.app) as client:
            doctor_token = main.token({'id': 1, 'role': 'doctor'})
            company_a_token = main.token({'id': 3, 'role': 'pharma', 'company_user_id': 101})
            rep_a_token = main.token({'id': 6, 'role': 'sales_rep', 'company_user_id': 101})
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

            doctor_assignment = client.patch(
                '/api/conversations/1',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'sales_representative_id': 7},
            )
            assert doctor_assignment.status_code == 403
            cross_company_assignment = client.post(
                '/api/conversations/1/assign',
                headers={'Authorization': f'Bearer {company_a_token}'},
                json={'sales_representative_id': 7},
            )
            assert cross_company_assignment.status_code == 400
            doctor_status_patch = client.patch(
                '/api/conversations/1',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'status': 'closed'},
            )
            assert doctor_status_patch.status_code == 400

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


def test_human_chat_creates_linked_ticket_and_scopes_status_updates():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        with TestClient(main.app) as client:
            doctor_token = main.token({'id': 1, 'role': 'doctor'})
            doctor_b_token = main.token({'id': 2, 'role': 'doctor'})
            company_a_token = main.token({'id': 3, 'role': 'pharma', 'company_user_id': 101})
            company_b_token = main.token({'id': 4, 'role': 'pharma', 'company_user_id': 102})
            rep_a_token = main.token({'id': 6, 'role': 'sales_rep', 'company_user_id': 101})
            rep_b_token = main.token({'id': 7, 'role': 'sales_rep', 'company_user_id': 102})

            with sqlite3.connect(db_path) as conn:
                conn.execute('UPDATE conversations SET company_id=3, company_user_id=101 WHERE id=1')
                conn.execute('UPDATE conversations SET sales_rep_id=NULL, sales_representative_id=NULL, assigned_at=NULL WHERE id=1')
                conn.execute('UPDATE conversations SET sales_rep_id=NULL, sales_representative_id=NULL, assigned_at=NULL WHERE id=2')
                conn.execute(
                    "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
                    ('Rep A2', 'rep.a2@test.local', main.phash('secret'), 'sales_rep', 'Company A', main.now(), 'approved', 101),
                )
                conn.commit()

            directory = client.get('/api/doctor/pharma-companies', headers={'Authorization': f'Bearer {doctor_token}'})
            assert directory.status_code == 200, directory.text
            assert {company['company_id'] for company in directory.json()} == {3, 4, 5}
            company_a = next(company for company in directory.json() if company['company_id'] == 3)
            assert company_a['reps_count'] == 2
            assert company_a['available_contact']
            handoff = client.post('/api/ai/human-handoff', headers={'Authorization': f'Bearer {doctor_token}'}, json={'message': 'Connect me to sales'})
            assert handoff.status_code == 200, handoff.text
            assert handoff.json()['status'] == 'company_selection'
            assert len(handoff.json()['companies']) == 3

            started = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 3},
            )
            assert started.status_code == 200, started.text
            conversation = started.json()
            ticket = conversation['ticket']
            assert ticket['conversation_id'] == conversation['id']
            assert ticket['doctor_id'] == 1
            assert ticket['company_id'] == 101
            assert ticket['sales_representative_id'] is None
            assert ticket['ticket_no'].startswith('TKT-')
            assert ticket['status'] == 'Open'
            reopened = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 3},
            )
            assert reopened.status_code == 200, reopened.text
            assert reopened.json()['id'] == conversation['id']
            assert reopened.json()['ticket_id'] == ticket['id']
            assert reopened.json()['company_id'] == 101

            rep_a2_token = main.token({'id': 9, 'role': 'sales_rep', 'company_user_id': 101})
            rep_a_available = client.get('/api/human-conversations', headers={'Authorization': f'Bearer {rep_a_token}'})
            rep_a2_available = client.get('/api/human-conversations', headers={'Authorization': f'Bearer {rep_a2_token}'})
            assert conversation['id'] in {item['id'] for item in rep_a_available.json()}
            assert conversation['id'] in {item['id'] for item in rep_a2_available.json()}
            unclaimed_message = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {rep_a_token}'},
                json={'content': 'I will take this case.'},
            )
            assert unclaimed_message.status_code == 409
            unclaimed_legacy_message = client.post(
                f'/api/conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {rep_a_token}'},
                json={'content': 'I will take this case.'},
            )
            assert unclaimed_legacy_message.status_code == 409
            claimed = client.post(f'/api/human-conversations/{conversation["id"]}/claim', headers={'Authorization': f'Bearer {rep_a_token}'})
            assert claimed.status_code == 200, claimed.text
            assert claimed.json()['sales_representative_id'] == 6
            assert claimed.json()['ticket_status'] == 'Assigned'
            competing_claim = client.post(f'/api/human-conversations/{conversation["id"]}/claim', headers={'Authorization': f'Bearer {rep_a2_token}'})
            assert competing_claim.status_code == 409
            assert 'already being handled' in competing_claim.json()['detail']
            assert client.get(f'/api/human-conversations/{conversation["id"]}', headers={'Authorization': f'Bearer {rep_a2_token}'}).status_code == 403
            cross_company_claim = client.post(f'/api/human-conversations/{conversation["id"]}/claim', headers={'Authorization': f'Bearer {rep_b_token}'})
            assert cross_company_claim.status_code == 403
            company_override = client.post(
                f'/api/conversations/{conversation["id"]}/assign',
                headers={'Authorization': f'Bearer {company_a_token}'},
                json={'sales_representative_id': 9},
            )
            assert company_override.status_code == 409
            peer_notifications = client.get('/api/notifications', headers={'Authorization': f'Bearer {rep_a2_token}'}).json()
            assert any(item['type'] == 'human_chat_assigned' for item in peer_notifications)
            assert client.get('/api/notifications', headers={'Authorization': f'Bearer {rep_b_token}'}).json() == []
            assert {item['id'] for item in client.get('/api/tickets', headers={'Authorization': f'Bearer {rep_a2_token}'}).json()} == {ticket['id']}
            assert client.get('/api/tickets', headers={'Authorization': f'Bearer {rep_b_token}'}).json() == []

            sent = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'content': 'I need help with this product.'},
            )
            assert sent.status_code == 200, sent.text
            rep_detail = client.get(
                f'/api/human-conversations/{conversation["id"]}',
                headers={'Authorization': f'Bearer {rep_a_token}'},
            )
            assert rep_detail.status_code == 200, rep_detail.text
            assert rep_detail.json()['messages'][0]['content'] == 'I need help with this product.'
            assert rep_detail.json()['ticket']['ticket_no'] == ticket['ticket_no']

            reply = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {rep_a_token}'},
                json={'content': 'I will share the approved product materials.'},
            )
            assert reply.status_code == 200, reply.text
            doctor_detail = client.get(
                f'/api/human-conversations/{conversation["id"]}',
                headers={'Authorization': f'Bearer {doctor_token}'},
            )
            assert len(doctor_detail.json()['messages']) == 2
            assert doctor_detail.json()['ticket_events'][-1]['event_type'] == 'representative_responded'
            assert client.get('/api/notifications', headers={'Authorization': f'Bearer {doctor_token}'}).json()[0]['title'] == 'New Human Support Message'

            assert client.get('/api/tickets', headers={'Authorization': f'Bearer {company_a_token}'}).json()[0]['ticket_no'] == ticket['ticket_no']
            assert client.get('/api/tickets', headers={'Authorization': f'Bearer {company_b_token}'}).json() == []
            assert client.get('/api/tickets', headers={'Authorization': f'Bearer {rep_b_token}'}).json() == []
            assert client.get(f'/api/human-conversations/{conversation["id"]}', headers={'Authorization': f'Bearer {rep_b_token}'}).status_code == 403
            assert client.get(f'/api/human-conversations/{conversation["id"]}', headers={'Authorization': f'Bearer {main.token({"id": 1, "role": "admin"})}'}).status_code == 403
            assert client.patch(f'/api/tickets/{ticket["id"]}', headers={'Authorization': f'Bearer {rep_b_token}'}, json={'status': 'CLOSED'}).status_code == 403
            assert client.patch(f'/api/tickets/{ticket["id"]}', headers={'Authorization': f'Bearer {company_b_token}'}, json={'status': 'CLOSED'}).status_code == 403

            changed = client.patch(
                f'/api/tickets/{ticket["id"]}',
                headers={'Authorization': f'Bearer {rep_a_token}'},
                json={'status': 'IN_PROGRESS'},
            )
            assert changed.status_code == 200, changed.text
            doctor_tickets = client.get('/api/tickets', headers={'Authorization': f'Bearer {doctor_token}'}).json()
            company_tickets = client.get('/api/tickets', headers={'Authorization': f'Bearer {company_a_token}'}).json()
            assert doctor_tickets[0]['status'] == 'In Progress'
            assert company_tickets[0]['status'] == 'In Progress'

            resolved = client.patch(
                f'/api/tickets/{ticket["id"]}',
                headers={'Authorization': f'Bearer {rep_a_token}'},
                json={'status': 'RESOLVED'},
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()['ticket']['status'] == 'Resolved'
            assert resolved.json()['ticket']['resolved_by'] == 6
            assert client.get('/api/tickets', headers={'Authorization': f'Bearer {doctor_token}'}).json()[0]['status'] == 'Resolved'
            assert any(item['title'] == 'Support request resolved' for item in client.get('/api/notifications', headers={'Authorization': f'Bearer {doctor_token}'}).json())
            resolved_message = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'content': 'I have another question.'},
            )
            assert resolved_message.status_code == 409
            assert conversation['id'] not in {item['id'] for item in client.get('/api/human-conversations', headers={'Authorization': f'Bearer {doctor_token}'}).json()}
            new_company_a_chat = client.post('/api/conversations', headers={'Authorization': f'Bearer {doctor_token}'}, json={'company_id': 3})
            assert new_company_a_chat.status_code == 200, new_company_a_chat.text
            assert new_company_a_chat.json()['id'] != conversation['id']
            assert new_company_a_chat.json()['ticket_id'] != ticket['id']

            company_b_start = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 4},
            )
            assert company_b_start.status_code == 200, company_b_start.text
            company_b_ticket = company_b_start.json()['ticket']
            assert company_b_start.json()['company_id'] == 102
            assert company_b_ticket['sales_representative_id'] is None
            assert {item['ticket_no'] for item in client.get('/api/tickets', headers={'Authorization': f'Bearer {company_a_token}'}).json()} == {ticket['ticket_no']}
            assert {item['ticket_no'] for item in client.get('/api/tickets', headers={'Authorization': f'Bearer {company_b_token}'}).json()} == {company_b_ticket['ticket_no']}
            company_b_claim = client.post(f'/api/human-conversations/{company_b_start.json()["id"]}/claim', headers={'Authorization': f'Bearer {rep_b_token}'})
            assert company_b_claim.status_code == 200, company_b_claim.text
            company_b_resolution = client.patch(
                f'/api/tickets/{company_b_ticket["id"]}',
                headers={'Authorization': f'Bearer {rep_b_token}'},
                json={'status': 'Resolved'},
            )
            assert company_b_resolution.status_code == 200, company_b_resolution.text
            assert company_b_resolution.json()['ticket']['status'] == 'Resolved'
            assert conversation['id'] not in {item['id'] for item in client.get('/api/human-conversations', headers={'Authorization': f'Bearer {doctor_token}'}).json()}

            denied = client.get(
                f'/api/human-conversations/{conversation["id"]}',
                headers={'Authorization': f'Bearer {doctor_b_token}'},
            )
            assert denied.status_code == 403
    finally:
        cleanup_temp_db(db_path)


def test_company_without_eligible_rep_opens_company_owned_waiting_conversation():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE users SET verification_status='pending' WHERE id=8")
            conn.commit()
        with TestClient(main.app) as client:
            doctor_token = main.token({'id': 1, 'role': 'doctor'})
            company_c_token = main.token({'id': 5, 'role': 'pharma', 'company_user_id': 103})
            directory = client.get('/api/doctor/pharma-companies', headers={'Authorization': f'Bearer {doctor_token}'})
            assert directory.status_code == 200, directory.text
            company = next(item for item in directory.json() if item['company_id'] == 5)
            assert not company['available_contact']
            assert company['reps_count'] == 0

            response = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 5},
            )
            assert response.status_code == 200, response.text
            conversation = response.json()
            assert conversation['id'] == 3
            assert conversation['sales_representative_id'] is None
            assert conversation['ticket_status'] == 'Open'

            repeated = client.post(
                '/api/conversations',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'company_id': 5},
            )
            assert repeated.status_code == 200, repeated.text
            assert repeated.json()['id'] == conversation['id']
            assert repeated.json()['ticket_id'] == conversation['ticket_id']
            with sqlite3.connect(db_path) as conn:
                assert conn.execute('SELECT COUNT(*) FROM tickets WHERE conversation_id=?', (conversation['id'],)).fetchone()[0] == 1
            sent = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {doctor_token}'},
                json={'content': 'Please route my request to company support.'},
            )
            assert sent.status_code == 200, sent.text
            company_detail = client.get(
                f'/api/human-conversations/{conversation["id"]}',
                headers={'Authorization': f'Bearer {company_c_token}'},
            )
            assert company_detail.status_code == 200, company_detail.text
            assert company_detail.json()['ticket']['status'] == 'Open'
            assert company_detail.json()['messages'][0]['content'] == 'Please route my request to company support.'
            reply = client.post(
                f'/api/human-conversations/{conversation["id"]}/messages',
                headers={'Authorization': f'Bearer {company_c_token}'},
                json={'content': 'A company support colleague will take this conversation.'},
            )
            assert reply.status_code == 200, reply.text
            doctor_detail = client.get(
                f'/api/human-conversations/{conversation["id"]}',
                headers={'Authorization': f'Bearer {doctor_token}'},
            )
            assert doctor_detail.json()['messages'][-1]['content'] == 'A company support colleague will take this conversation.'
            chats = client.get('/api/human-conversations', headers={'Authorization': f'Bearer {doctor_token}'}).json()
            assert {chat['id'] for chat in chats} == {1, 2, 3}
    finally:
        cleanup_temp_db(db_path)


def test_ai_escalation_reuses_ticket_and_converts_the_owned_ai_thread():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        issue = 'I have an allergic reaction and need help.'
        with sqlite3.connect(db_path) as conn:
            agent_id = conn.execute(
                "INSERT INTO conversations(user_id,role,conversation_type,created_at) VALUES(?,?,?,?)",
                (2, 'doctor', 'agent', main.now()),
            ).lastrowid
            conn.execute(
                'INSERT INTO messages(conversation_id,sender,agent,content,risk,created_at) VALUES(?,?,?,?,?,?)',
                (agent_id, 'user', '', issue, '', main.now()),
            )
            conn.execute(
                'INSERT INTO messages(conversation_id,sender,agent,content,risk,created_at) VALUES(?,?,?,?,?,?)',
                (agent_id, 'agent', 'Risk & Escalation Agent', 'This needs qualified human review.', 'critical', main.now()),
            )
            conn.execute(
                'INSERT INTO medicines(name,category,price,description,stock,status,created_at,owner_user_id,company) VALUES(?,?,?,?,?,?,?,?,?)',
                ('Company A Product', 'General', 100, 'Test product', 10, 'Active', main.now(), 101, 'Company A'),
            )
            conn.execute(
                'INSERT INTO medicines(name,category,price,description,stock,status,created_at,owner_user_id,company) VALUES(?,?,?,?,?,?,?,?,?)',
                ('Company B Product', 'General', 100, 'Test product', 10, 'Active', main.now(), 102, 'Company B'),
            )
            conn.commit()
        c = main.db()
        doctor = main.row(c.execute('SELECT * FROM users WHERE id=2').fetchone())
        c.close()
        ai_escalation = main.agent_answer(doctor, issue)
        assert ai_escalation['risk'] == 'critical'
        doctor_token = main.token({'id': 2, 'role': 'doctor'})
        headers = {'Authorization': f'Bearer {doctor_token}'}
        with TestClient(main.app) as client:
            handoff = client.post('/api/ai/human-handoff', headers=headers, json={'message': issue, 'conversation_id': agent_id})
            assert handoff.status_code == 200, handoff.text
            started = client.post(
                '/api/conversations',
                headers=headers,
                json={'company_id': 3, 'medicine_id': 1, 'issue': issue, 'agent_conversation_id': agent_id},
            )
            assert started.status_code == 200, started.text
            conversation = started.json()
            assert conversation['id'] == agent_id
            assert conversation['conversation_type'] == 'human'
            assert conversation['doctor_id'] == 2
            assert conversation['company_id'] == 101
            assert conversation['medicine_id'] == 1
            assert conversation['ticket']['priority'] == 'Critical'
            assert conversation['ticket']['content'] == issue
            detail = client.get(f'/api/human-conversations/{agent_id}', headers=headers)
            assert detail.status_code == 200, detail.text
            assert len(detail.json()['messages']) == 2
            reopened = client.post('/api/conversations', headers=headers, json={'company_id': 3, 'medicine_id': 1})
            assert reopened.status_code == 200, reopened.text
            assert reopened.json()['id'] == agent_id
            second_issue = 'I have a severe side effect and need human help again.'
            with sqlite3.connect(db_path) as conn:
                second_agent_id = conn.execute(
                    "INSERT INTO conversations(user_id,role,conversation_type,created_at) VALUES(?,?,?,?)",
                    (2, 'doctor', 'agent', main.now()),
                ).lastrowid
                conn.execute(
                    'INSERT INTO messages(conversation_id,sender,agent,content,risk,created_at) VALUES(?,?,?,?,?,?)',
                    (second_agent_id, 'user', '', second_issue, '', main.now()),
                )
                conn.execute(
                    'INSERT INTO messages(conversation_id,sender,agent,content,risk,created_at) VALUES(?,?,?,?,?,?)',
                    (second_agent_id, 'agent', 'Risk & Escalation Agent', 'This needs qualified human review.', 'critical', main.now()),
                )
                conn.commit()
            main.agent_answer(doctor, second_issue)
            second_escalation = client.post(
                '/api/conversations',
                headers=headers,
                json={'company_id': 3, 'medicine_id': 1, 'issue': second_issue, 'agent_conversation_id': second_agent_id},
            )
            assert second_escalation.status_code == 200, second_escalation.text
            assert second_escalation.json()['id'] == agent_id
            assert second_escalation.json()['ticket_id'] == conversation['ticket']['id']
            assert second_escalation.json()['ticket']['priority'] == 'Critical'
            assert second_issue in second_escalation.json()['ticket']['content']
            imported_detail = client.get(f'/api/human-conversations/{agent_id}', headers=headers)
            assert any(message['content'] == second_issue for message in imported_detail.json()['messages'])
            with sqlite3.connect(db_path) as conn:
                imported_count = conn.execute('SELECT COUNT(*) FROM messages WHERE conversation_id=? AND source_message_id IS NOT NULL', (agent_id,)).fetchone()[0]
            assert imported_count == 2
            repeated_import = client.post(
                '/api/conversations',
                headers=headers,
                json={'company_id': 3, 'medicine_id': 1, 'issue': second_issue, 'agent_conversation_id': second_agent_id},
            )
            assert repeated_import.status_code == 200, repeated_import.text
            with sqlite3.connect(db_path) as conn:
                assert conn.execute('SELECT COUNT(*) FROM messages WHERE conversation_id=? AND source_message_id IS NOT NULL', (agent_id,)).fetchone()[0] == imported_count
            invalid_medicine = client.post('/api/conversations', headers=headers, json={'company_id': 3, 'medicine_id': 2})
            assert invalid_medicine.status_code == 400
        with sqlite3.connect(db_path) as conn:
            assert conn.execute('SELECT COUNT(*) FROM tickets WHERE conversation_id=?', (agent_id,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM tickets WHERE status='Closed' AND subject LIKE 'Merged into %'").fetchone()[0] == 1
    finally:
        cleanup_temp_db(db_path)


def test_simultaneous_representative_claims_have_one_winner():
    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute('UPDATE conversations SET sales_rep_id=NULL,sales_representative_id=NULL,assigned_at=NULL WHERE id=1')
            conn.execute(
                "INSERT INTO users(name,email,password,role,company,created_at,verification_status,company_user_id) VALUES(?,?,?,?,?,?,?,?)",
                ('Rep A2', 'rep.a2@race.test', main.phash('secret'), 'sales_rep', 'Company A', main.now(), 'approved', 101),
            )
            conn.commit()
        doctor_token = main.token({'id': 1, 'role': 'doctor'})
        with TestClient(main.app) as client:
            started = client.post('/api/conversations', headers={'Authorization': f'Bearer {doctor_token}'}, json={'company_id': 3})
            assert started.status_code == 200, started.text
            conversation_id = started.json()['id']
        tokens = [
            main.token({'id': 6, 'role': 'sales_rep', 'company_user_id': 101}),
            main.token({'id': 9, 'role': 'sales_rep', 'company_user_id': 101}),
        ]

        def claim(token):
            try:
                main.claim_human_conversation(conversation_id, f'Bearer {token}')
                return 200
            except main.HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(claim, tokens))
        assert sorted(statuses) == [200, 409]
        c = main.db()
        conversation = c.execute('SELECT * FROM conversations WHERE id=?', (conversation_id,)).fetchone()
        ticket = c.execute('SELECT * FROM tickets WHERE conversation_id=?', (conversation_id,)).fetchone()
        c.close()
        assert conversation['sales_representative_id'] in (6, 9)
        assert ticket['sales_representative_id'] == conversation['sales_representative_id']
        assert ticket['status'] == 'Assigned'
    finally:
        cleanup_temp_db(db_path)


def test_synthetic_human_chat_seed_is_idempotent_and_uses_existing_users():
    from backend.seed_demo_human_chat import seed_demo_human_chat

    db_path = setup_temp_db()
    try:
        seed_company_chat_data(db_path)
        first = seed_demo_human_chat()
        second = seed_demo_human_chat()
        assert first['conversation_id'] == second['conversation_id']
        assert first['ticket_no'] == second['ticket_no']
        with sqlite3.connect(db_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM conversations WHERE conversation_type='human'").fetchone()[0] == 4
            assert conn.execute("SELECT COUNT(*) FROM tickets WHERE conversation_id=?", (first['conversation_id'],)).fetchone()[0] == 1
            assert conn.execute('SELECT COUNT(*) FROM messages WHERE conversation_id=?', (first['conversation_id'],)).fetchone()[0] == 4
            assert conn.execute("SELECT subject FROM tickets WHERE conversation_id=?", (first['conversation_id'],)).fetchone()[0] == 'DEMO / SYNTHETIC CONVERSATION'
    finally:
        cleanup_temp_db(db_path)
