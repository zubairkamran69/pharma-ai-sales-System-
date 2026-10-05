# PharmaAI Human Company Chat Workflow

## Doctor
1. Doctor opens **Company Chats**.
2. Only owner-verified pharmaceutical companies appear in the company directory.
3. Each company shows its unread count.
4. Clicking Chat creates/reuses only the current active conversation for that doctor + company. A closed conversation is never reopened.
5. Every human conversation has a unique support ticket (`TKT-xxxx`) linked to the conversation.

## Sales representatives
1. Every eligible representative of the selected company is notified when a doctor starts a new support request.
2. All representatives of that company can see an unassigned request.
3. The first representative to claim it wins the assignment atomically.
4. The assigned representative can send messages and update the ticket.
5. Other representatives are notified that the case is being handled and cannot open/send messages in that private conversation.

## Pharmaceutical company
The owning pharmaceutical company can see its own doctors' active support conversations and the linked ticket. It can send messages and mark the ticket resolved. It cannot access another company's conversations.

## Privacy
- Doctor: only their own human conversations.
- Pharma company: only conversations belonging to its company.
- Sales representative: only their company's conversations; after assignment, only the assigned conversation is readable.
- Platform owner/admin: human doctor-company chats are intentionally excluded.

## Resolution lifecycle
- Doctor, assigned sales representative, or owning pharmaceutical company can mark an active ticket **Resolved**.
- Resolution closes both the ticket and the linked conversation.
- Closed conversations disappear from active Company Chats / Doctor Chats.
- Closed tickets remain in ticket history for auditability.
- Sending a message to a closed conversation is rejected.
- A later Chat action creates a new conversation and a new ticket; the old conversation is not reopened or reused.
