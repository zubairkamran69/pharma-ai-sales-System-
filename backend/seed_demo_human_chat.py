"""Create one clearly labeled synthetic human-chat thread in the configured database.

Run from the repository root with:
    python -m backend.seed_demo_human_chat
"""

import os
import secrets

from backend import main


def seed_demo_human_chat():
    main.init()
    c = main.db()
    doctor_row = c.execute(
        "SELECT * FROM users WHERE role='doctor' AND verification_status IN ('approved','verified','demo') ORDER BY CASE WHEN email='doctor@pharmaai.demo' THEN 0 ELSE 1 END,id LIMIT 1"
    ).fetchone()
    company_row = c.execute(
        "SELECT * FROM users WHERE role='pharma' AND verification_status IN ('approved','verified','demo') ORDER BY id LIMIT 1"
    ).fetchone()
    if not doctor_row or not company_row:
        c.close()
        raise RuntimeError('A verified doctor and pharmaceutical company must already exist in the configured database.')

    doctor = main.row(doctor_row)
    company = main.row(company_row)
    company_scope_id = company.get('company_user_id') or company['id']
    representative = c.execute(
        "SELECT * FROM users WHERE role='sales_rep' AND company_user_id=? AND verification_status IN ('approved','verified','demo') ORDER BY id LIMIT 1",
        (company_scope_id,),
    ).fetchone()
    if representative:
        representative = main.row(representative)
    else:
        company_name = company.get('company') or company['name']
        sales_id = main.generate_sales_id(c, company_name)
        password = os.getenv('DEMO_USER_PASSWORD') or secrets.token_urlsafe(32)
        representative_id = c.execute(
            '''INSERT INTO users(name,email,password,role,company,created_at,verification_status,
                                 job_title,company_user_id,phone,sales_id,registration_number)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            ('DEMO Sales Representative', f'demo-human-rep-{company_scope_id}@pharmaai.local',
             main.phash(password), 'sales_rep', company_name, main.now(), 'demo',
             'DEMO / SYNTHETIC Sales Representative', company_scope_id, '', sales_id, sales_id),
        ).lastrowid
        representative = main.row(c.execute('SELECT * FROM users WHERE id=?', (representative_id,)).fetchone())

    medicine = c.execute(
        'SELECT * FROM medicines WHERE owner_user_id IN (?,?) ORDER BY id LIMIT 1',
        (company['id'], company_scope_id),
    ).fetchone()
    medicine_id = medicine['id'] if medicine else None
    conversation = c.execute(
        '''SELECT conv.* FROM conversations conv
           JOIN tickets demo_ticket ON demo_ticket.conversation_id=conv.id
           WHERE demo_ticket.subject='DEMO / SYNTHETIC CONVERSATION'
             AND conv.conversation_type='human' AND conv.doctor_id=?
             AND COALESCE(conv.company_id,conv.company_user_id)=?
             AND COALESCE(conv.medicine_id,-1)=COALESCE(?,-1)
           ORDER BY conv.id LIMIT 1''',
        (doctor['id'], company_scope_id, medicine_id),
    ).fetchone()
    if conversation:
        conversation_id = conversation['id']
        c.execute(
            'UPDATE conversations SET company_id=?,company_user_id=?,sales_representative_id=?,sales_rep_id=?,medicine_id=COALESCE(medicine_id,?),updated_at=? WHERE id=?',
            (company_scope_id, company_scope_id, representative['id'], representative['id'], medicine_id, main.now(), conversation_id),
        )
    else:
        timestamp = main.now()
        conversation_id = c.execute(
            '''INSERT INTO conversations(user_id,role,conversation_type,doctor_id,company_id,company_user_id,
                                         sales_rep_id,sales_representative_id,medicine_id,status,created_at,
                                         updated_at,last_message_at,assigned_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (doctor['id'], 'doctor', 'human', doctor['id'], company_scope_id, company_scope_id,
             representative['id'], representative['id'], medicine_id, 'open', timestamp,
             timestamp, timestamp, timestamp),
        ).lastrowid

    company_name = company.get('company') or company['name']
    ticket, _ = main._create_human_ticket(
        c, doctor, company_scope_id, f'DEMO / SYNTHETIC · {company_name}',
        representative['id'], conversation_id, medicine_id,
    )
    c.execute(
        "UPDATE tickets SET subject=?,content=? WHERE id=?",
        ('DEMO / SYNTHETIC CONVERSATION', 'Synthetic demonstration support ticket. No real product advice or patient data.', ticket['id']),
    )
    if not c.execute('SELECT id FROM messages WHERE conversation_id=? LIMIT 1', (conversation_id,)).fetchone():
        medicine_name = medicine['name'] if medicine else 'the company product information'
        samples = [
            (doctor, f'[DEMO / SYNTHETIC CONVERSATION] Hello, I would like more information about {medicine_name}.'),
            (representative, f'[DEMO / SYNTHETIC CONVERSATION] Hello Doctor. This is a synthetic demo reply from {company_name}; no clinical guidance is provided.'),
            (doctor, '[DEMO / SYNTHETIC CONVERSATION] Can you share the approved information available in your company library?'),
            (representative, '[DEMO / SYNTHETIC CONVERSATION] I can direct you to the approved company materials available in this demo system.'),
        ]
        for sender, content in samples:
            c.execute(
                '''INSERT INTO messages(conversation_id,sender,sender_id,sender_role,agent,message,content,risk,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?)''',
                (conversation_id, 'human', sender['id'], sender['role'], sender['name'], content, content, 'demo', main.now()),
            )

    c.commit()
    result = {'conversation_id': conversation_id, 'ticket_no': ticket['ticket_no'], 'representative': representative['name']}
    c.close()
    return result


if __name__ == '__main__':
    print(seed_demo_human_chat())