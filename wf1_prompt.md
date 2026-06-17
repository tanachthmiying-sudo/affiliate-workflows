# WF1: Video Status Tracker
# Usage in Claude Code: paste this prompt, fill timeframe, drag TikTok file

I need you to run the Video Status Tracker workflow for Migo Thailand Affiliate team.

Timeframe: [type "last week" or "June" or "2024-06-01 to 2024-06-15"]

Here is my TikTok Seller export data: [drag your file here]

Please do the following:

1. Read the attached TikTok file and detect the column names automatically

2. Connect to Feishu Base "AFS Central Team Testing" using credentials 
   in config.yaml (FEISHU_APP_ID and FEISHU_APP_SECRET)

3. Read all records from "Creator's Pool" table
   - Filter only rows where "Date of Contact" falls within the timeframe
   - Extract: Creator ID, Creator Name, AFS Owner (the staff column 
     already in Creator's Pool), Date of Contact, and Record ID

4. Match TikTok data to Creator's Pool records using Creator ID
   - Case insensitive, ignore "@" prefix and whitespace
   - MATCHED: has TikTok video data → update with performance
   - NOT POSTED: in Creator's Pool for this timeframe but no TikTok data found

5. Add these columns to "Creator's Pool" immediately after "Date of Contact"
   if they don't exist yet — do NOT remove any existing column:

   Video Status        (singleSelect: Posted / Pending / Not Posted)
   Video ID            (text)
   Video Title         (text)
   Post Date           (dateTime)
   Views               (number)
   Likes               (number)
   Comments            (number)
   Shares              (number)
   Orders              (number)
   GMV (THB)           (number)
   Growth Potential    (singleSelect: 🔥 High / ⚡ Medium / ⬇ Low)
   Boost Recommended   (checkbox)
   AFS Conversion Rate (text)
   Last Updated        (dateTime)

6. Compute for each matched row:
   - Growth Potential:
       🔥 High   → views > 50,000 OR gmv > 5,000 OR orders > 50
       ⚡ Medium → views > 10,000 OR gmv > 1,000 OR orders > 10
       ⬇ Low    → everything else
   - Boost Recommended = true if Growth Potential is 🔥 High
   - Creators with no TikTok data → Video Status = "Not Posted",
     leave performance columns blank

7. Calculate Junior AFS conversion rate using the AFS Owner column
   already in Creator's Pool:
   - Group by AFS Owner name
   - Contacted = total creators assigned to them within timeframe
   - Posted = how many posted at least 1 video
   - Rate = Posted ÷ Contacted × 100
   - Write into AFS Conversion Rate column as "7/10 (70%)"

8. Write all updates to Creator's Pool using batch update

9. Print this summary when done:

   📅 TIMEFRAME: [date_start] → [date_end]

   📋 POSTING COMPLETENESS
      ✅ Posted:       X (X%)
      ❌ Not Posted:   X (X%)
      [List Not Posted: Creator Name | AFS Owner]

   📊 VIDEO PERFORMANCE
      🔥 High potential:   X
      ⚡ Medium potential: X
      ⬇ Low potential:    X
      Total GMV: ฿X,XXX

   🚀 TOP 5 BOOST CANDIDATES
      [Creator Name | Video Title | Views | GMV]

   🎯 AFS CONVERSION RATE
      [AFS Name | Contacted | Posted | Rate]

   ✅ Total records updated in Creator's Pool: X
