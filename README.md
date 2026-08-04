# Smart Bin Retrofit

A universal clip-on retrofit device (ultrasonic fill sensor + small LCD) that
attaches to any existing bin, reports fill level, and uses an AI agent to
flag genuinely-full vs. obstructed vs. abnormal readings.

## Team & Tasks

### Mary Garcia — Front-end / Design / Documentation
- Create case to house the device
- Create GitHub repo
- Build the dashboard (fill gauge, history chart, pickup queue)
- Add approve/reject buttons and a log of past decisions
- Make the dashboard look clean and easy to use
- Design the demo poster
- Compile/format the team's proposal sections

### Jared Lopez — Edge Device
- Hook up the sensor and screen to the mini-computer
- Turn raw sensor readings into a clean fill percentage
- Show live fill % on the LCD
- Make the sensor start automatically when it boots
- Save readings locally if the internet drops, and send them later

### Utsanakorn "Kate" Chinkonglar — Cloud Platform (Azure)
- Build the cloud endpoint that receives and checks readings
- Set up storage for the reading history
- Keep passwords and keys out of the code
- Set up error logging and a health check
- Set up the deploy pipeline so it's live on a public link

### Anh Quan Pham — AI Agent
- Build the AI agent in Azure AI Foundry: role, instructions, behavior
- Decide what info the agent outputs (fill %, confidence, action)
- Make the agent learn each bin's range on its own (auto-calibration)
- Make the agent catch weird or blocked readings
- Build the full flow: check, ask agent, route, approve, log
- Make sample data and write five test cases

### Parneet Kaur — Testing & Hardware Support
- Make fake test data for the team to build with
- Test-fit the sensor in the printed mount, confirm sight line
- Help Jared put the hardware together (wiring, breadboard)
- Set up demo backups (spare hotspot, test-event button)

### Reading (edge device → cloud)
```json
{
  "bin_id": "string",
  "timestamp": "ISO 8601 string",
  "fill_percent": 0-100,
  "raw_distance_cm": "number",
  "battery_percent": 0-100,
  "status": "ok | obstructed | error"
}
```

### Agent output (AI agent → dashboard)
```json
{
  "bin_id": "string",
  "timestamp": "ISO 8601 string",
  "classification": "full | not_full | obstructed | anomaly",
  "confidence": 0.0-1.0,
  "recommendation": "string",
  "requires_human_approval": true
}
```

### Dashboard expects (from cloud API)
```json
{
  "bins": [
    {
      "bin_id": "string",
      "location": "string",
      "fill_percent": 0-100,
      "classification": "full | not_full | obstructed | anomaly",
      "last_updated": "ISO 8601 string",
      "recommendation": "string | null"
    }
  ]
}
```

## Repo structure
- `/dashboard` — React front-end (Mary)
- `/edge-device` — sensor/Pi firmware (Jared)
- `/agent` — AI agent & workflow (Anh Quan)
- `/infra` — Azure config/deployment (Kate)

## Status
- [ ] Data contract locked (currently draft)
- [ ] Mock data available for dashboard dev
- [ ] Azure resources provisioned
- [ ] Edge device sending real readings
- [ ] Agent classification live
