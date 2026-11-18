-- The five starting shops from the brief. All public, no customer accounts.

INSERT INTO shops (name, url, host, type, country, currency, provides, note) VALUES
    ('Uhlig', 'https://www.uhlig-kakteen.de/', 'uhlig-kakteen.de', 'nursery', 'DE', 'EUR',
     '{"availability": true}', 'JTL shop, availability only.'),
    ('FlorAccess', 'https://www.floraccess.com/', 'floraccess.com', 'wholesaler', NULL, 'EUR',
     '{"quantity": true}', 'Wholesaler with quantities.'),
    ('Kakteen-Haage', 'https://www.kakteen-haage.de/', 'kakteen-haage.de', 'nursery', 'DE', 'EUR',
     '{}', 'RSS feed of the Hoya category.'),
    ('Jungle Leaves', 'https://jungle-leaves.de/', 'jungle-leaves.de', 'retailer', 'DE', 'EUR',
     '{}', 'Shopify, Hoyas under "Sukkulenten".'),
    ('Ben''s Jungle', 'https://bens-jungle.com/', 'bens-jungle.com', 'retailer', NULL, NULL,
     '{}', '');
