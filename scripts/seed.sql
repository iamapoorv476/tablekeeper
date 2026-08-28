-- Seed data: one fictional restaurant, tables, house rules, and a returning guest.
-- Replace the guest phone_number with your own number before the real demo call.

insert into restaurants (id, name, phone_number, timezone, opening_time, closing_time)
values ('11111111-1111-1111-1111-111111111111', 'Basilico Trattoria', '+910000000000', 'Asia/Kolkata', '11:00', '23:00')
on conflict (id) do nothing;

insert into tables (restaurant_id, label, seats) values
('11111111-1111-1111-1111-111111111111', 'T1', 2),
('11111111-1111-1111-1111-111111111111', 'T2', 2),
('11111111-1111-1111-1111-111111111111', 'T3', 4),
('11111111-1111-1111-1111-111111111111', 'T4', 4),
('11111111-1111-1111-1111-111111111111', 'T5', 6),
('11111111-1111-1111-1111-111111111111', 'Patio-1', 6)
on conflict do nothing;

insert into house_rules (restaurant_id, category, question_tags, content) values
('11111111-1111-1111-1111-111111111111', 'menu', array['signature','recommendation'],
  'Our signature dish is the truffle tagliatelle. Popular starters include burrata with heirloom tomatoes and the wood-fired focaccia.'),
('11111111-1111-1111-1111-111111111111', 'dietary', array['vegan','vegetarian'],
  'We have a full vegan menu including a vegan lasagna and a mushroom risotto made without butter or cheese.'),
('11111111-1111-1111-1111-111111111111', 'dietary', array['gluten-free','celiac'],
  'Gluten-free pasta is available as a substitute on any pasta dish at no extra charge. We also have gluten-free bread.'),
('11111111-1111-1111-1111-111111111111', 'policy', array['cancellation','no-show'],
  'Reservations are held for 15 minutes past the booked time before the table may be released.'),
('11111111-1111-1111-1111-111111111111', 'policy', array['large-party','group'],
  'Parties larger than 8 require a deposit and should call at least 24 hours in advance.'),
('11111111-1111-1111-1111-111111111111', 'policy', array['dress-code'],
  'Smart casual is preferred; there is no strict dress code.')
on conflict do nothing;

-- Returning guest for the "recognize the caller" demo.
-- IMPORTANT: replace this phone number with the number you'll actually call FROM during the demo.
insert into guests (restaurant_id, phone_number, name, preferences) values
('11111111-1111-1111-1111-111111111111', '+918957104430', 'Aarav Shah', 'usually asks for a window seat, prefers still water')
on conflict (restaurant_id, phone_number) do nothing;