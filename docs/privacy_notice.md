# Privacy notice — RAQIB / MUSHRIF camera analytics

**Who we are.** RAQIB (retail) and MUSHRIF (factory) are operations-analytics systems operated by the site owner. This notice describes what the system does with camera images and what it never does.

## What the cameras are used for

Counting people entering an area, measuring how many people wait at a checkout, whether a shelf face is empty, whether a person is inside a marked machine exclusion zone, whether a worker in a work area is wearing a helmet, and whether a machine is running. That is the complete list.

## What leaves the camera

Only **events**: a timestamp, a camera name, a zone name, a count or a class label (for example "person", "no helmet"), a model confidence, and the rule that fired. A 10-second **clip** is kept for warning and critical events so a supervisor can verify them. Every person's head in every stored or transmitted frame is pixelated and blurred before the frame is written anywhere.

## What the system never does

- No face recognition, no identity matching, no watch-lists.
- No tracking of a person across cameras or across days. Tracking numbers exist only inside one running session to count and measure; they are not stored with identity and reset when the process restarts.
- No audio.
- No sale of data, no sharing with third parties beyond the hosting providers listed below.
- The AI agent that proposes actions never sees video. It receives event summaries only.

## Retention

| Data | Kept for | Where |
|---|---|---|
| Events (counts, classes, confidences) | 13 months, for seasonal forecasting | Site database (Supabase, EU/ME region as configured) |
| Clips (faces blurred) | 30 days, then deleted | Cloud API storage |
| Raw video | Not stored by this system. The site's existing CCTV retention applies. | — |

## Hosting

Cloud API on Render, database on Supabase, dashboard on Vercel. Processing of video happens on a computer on the premises; only events and blurred clips are uploaded.

## Your rights

Employees and visitors can ask the site manager which events were recorded in a given period and request deletion of a clip. Because no identity is stored, the system cannot search by person; requests are handled by time and camera.

## Signage

Sites display a notice at entrances: "Cameras in this area are used for queue, safety, and stock analytics. Faces are blurred; no identification is performed. Details: [site contact]."

## Contact

Data controller: the site owner. Technical contact for this deployment: Krishna Mathur, project owner.

_This notice is a draft for the pilot and must be reviewed by the site's legal or HR function before deployment. UAE PDPL and the site's employment policies apply._
