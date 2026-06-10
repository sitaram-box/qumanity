# Key API Endpoints

## Authentication
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/register` | POST | Create new user |
| `/api/login` | POST | Authenticate user |
| `/api/logout` | POST | End session |
| `/api/recovery/verify` | POST | Password/ID recovery via birth location |

## Posts
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/posts` | GET | Fetch posts for current level |
| `/api/post/create` | POST | Create new post |
| `/api/post/vote` | POST | Vote on a post (+1/0/-1) |

## Economy
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/qoin/balance` | GET | Get wallet balance |
| `/api/qoin/transfer` | POST | Transfer Qoins (weekly settlement) |
| `/api/qoin/transactions` | GET | Transaction history |
| `/api/karma/claim` | POST | Submit karma claim |

## Elections
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/election/status` | GET | Get current election phase |
| `/api/election/nominate` | POST | Submit candidacy |
| `/api/election/vote` | POST | Vote for candidate |
| `/api/admin/nomination/approve` | POST | Approve nomination (admin only) |
| `/api/admin/nomination/reject` | POST | Reject nomination (admin only) |

## Family & Social
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/family/tree` | GET | Get family tree data |
| `/api/family/add_member` | POST | Add family member |
| `/api/connection/request` | POST | Send family/social request |
| `/api/connection/accept` | POST | Accept connection request |

## Messaging
| Endpoint | Method | Purpose |
| :--- | :--- | :--- |
| `/api/messages/inbox` | GET | Get received messages |
| `/api/messages/send` | POST | Send new message |
| `/api/messages/read` | POST | Mark message as read |
