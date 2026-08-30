 SELECT
    serial_no,
    user_ref_id,
    jsonb_pretty(premium_waterfall) AS premium_waterfall,
    jsonb_pretty(supporting_data) AS supporting_data
  FROM underwriting_final_calculations
  WHERE serial_no = 136;



  SELECT
    boost_discount_flow,
    created_at,
    updated_at
  FROM marigin_flows
  WHERE user_ref_id = 'SP-USER-920119';

  SELECT * FROM public.marigin_flows WHERE user_ref_id = 'SP-USER-121159'


    SELECT *
  FROM claims
  WHERE claim_id = 'CLM-SG-2026-000064';

    DELETE FROM claims
  WHERE claim_id = 'CLM-SG-2026-000066'
  RETURNING *;

