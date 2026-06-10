-- Seed categories for VELCS
-- Run after schema.sql

INSERT INTO categories (slug, name_en, name_hi, icon, kind, sort_order) VALUES
  ('travel', 'Travel', 'यातायात', 'car', 'service', 1),
  ('food', 'Food', 'खाना', 'utensils', 'product', 2),
  ('labour', 'Labour', 'मजदूरी', 'hard-hat', 'employment', 3),
  ('education', 'Education', 'शिक्षा', 'book-open', 'service', 4),
  ('repair', 'Repair', 'मरम्मत', 'wrench', 'service', 5),
  ('health', 'Health', 'स्वास्थ्य', 'heart-pulse', 'service', 6),
  ('women-services', 'Women Services', 'महिला सेवाएं', 'sparkles', 'service', 7),
  ('delivery', 'Delivery', 'डिलीवरी', 'truck', 'delivery', 8)
ON CONFLICT (slug) DO NOTHING;

-- Travel subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'service', p.id, v.sort_order
FROM categories p,
(VALUES
  ('rickshaw', 'Rickshaw', 'रिक्शा', 'bike', 1),
  ('auto', 'Auto', 'ऑटो', 'car', 2),
  ('bike-taxi', 'Bike Taxi', 'बाइक टैक्सी', 'bike', 3),
  ('cab-driver', 'Cab Driver', 'कैब ड्राइवर', 'car', 4),
  ('goods-transport', 'Goods Transport', 'माल ढulाई', 'truck', 5)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'travel'
ON CONFLICT (slug) DO NOTHING;

-- Food subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'product', p.id, v.sort_order
FROM categories p,
(VALUES
  ('fruits', 'Fruits', 'फल', 'apple', 1),
  ('vegetables', 'Vegetables', 'सब्जियां', 'carrot', 2),
  ('milk', 'Milk', 'दूध', 'milk', 3),
  ('homemade-food', 'Homemade Food', 'घर का खाना', 'home', 4),
  ('street-food', 'Street Food', 'स्ट्रीट फूड', 'store', 5),
  ('bakery', 'Bakery', 'बेकरी', 'croissant', 6)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'food'
ON CONFLICT (slug) DO NOTHING;

-- Labour subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'employment', p.id, v.sort_order
FROM categories p,
(VALUES
  ('construction', 'Construction', 'निर्माण', 'building', 1),
  ('farming', 'Farming', 'खेती', 'wheat', 2),
  ('domestic-work', 'Domestic Work', 'घरेलू काम', 'home', 3),
  ('loaders', 'Loaders', 'हमाल', 'package', 4)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'labour'
ON CONFLICT (slug) DO NOTHING;

-- Education subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'service', p.id, v.sort_order
FROM categories p,
(VALUES
  ('tuition', 'Tuition', 'ट्यूशन', 'graduation-cap', 1),
  ('computer-training', 'Computer Training', 'कंप्यूटर प्रशिक्षण', 'monitor', 2),
  ('language-classes', 'Language Classes', 'भाषा कक्षाएं', 'languages', 3)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'education'
ON CONFLICT (slug) DO NOTHING;

-- Repair subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'service', p.id, v.sort_order
FROM categories p,
(VALUES
  ('mobile-repair', 'Mobile Repair', 'मोबाइल मरम्मत', 'smartphone', 1),
  ('electrician', 'Electrician', 'इलेक्ट्रीशियन', 'zap', 2),
  ('plumber', 'Plumber', 'प्लंबर', 'droplets', 3),
  ('mechanic', 'Mechanic', 'मैकेनिक', 'cog', 4)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'repair'
ON CONFLICT (slug) DO NOTHING;

-- Health subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'service', p.id, v.sort_order
FROM categories p,
(VALUES
  ('nurse', 'Nurse', 'नर्स', 'stethoscope', 1),
  ('caretaker', 'Caretaker', 'देखभालकर्ता', 'heart', 2),
  ('ayurveda', 'Ayurveda', 'आयुर्वेद', 'leaf', 3)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'health'
ON CONFLICT (slug) DO NOTHING;

-- Women Services subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'service', p.id, v.sort_order
FROM categories p,
(VALUES
  ('tailoring', 'Tailoring', 'सिलाई', 'scissors', 1),
  ('mehendi', 'Mehendi', 'मेहंदी', 'paintbrush', 2),
  ('beauty-services', 'Beauty Services', 'ब्यूटी सेवाएं', 'sparkles', 3)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'women-services'
ON CONFLICT (slug) DO NOTHING;

-- Delivery subcategories
INSERT INTO categories (slug, name_en, name_hi, icon, kind, parent_id, sort_order)
SELECT v.slug, v.name_en, v.name_hi, v.icon, 'delivery', p.id, v.sort_order
FROM categories p,
(VALUES
  ('food-delivery', 'Food Delivery', 'खाना डिलीवरी', 'utensils', 1),
  ('product-delivery', 'Product Delivery', 'सामान डिलीवरी', 'package', 2),
  ('medicine-delivery', 'Medicine Delivery', 'दवा डिलीवरी', 'pill', 3)
) AS v(slug, name_en, name_hi, icon, sort_order)
WHERE p.slug = 'delivery'
ON CONFLICT (slug) DO NOTHING;
