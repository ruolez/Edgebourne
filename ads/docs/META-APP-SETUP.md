# Meta developer app and System User: setup guide

For the Edge Bourne Ads Console (`ads.edgebourne.com`). Do parts A–F now; part G
(webhook) waits until the dashboard is deployed, because Meta calls the URL when you save it.

**Rule: never paste the App Secret, a token, or a password into chat.** You type them into
the dashboard yourself (Settings → Meta / Email, stored encrypted) and, for Claude's CLI,
into your local `meta-ads/.env`. When a step is done, just tell Claude "done".

IDs you'll need (not secret):

| What | ID |
|---|---|
| Business portfolio "Edge Bourne Consulting" | 2289619248494805 |
| Facebook Page "Edge Bourne Consulting" | 1404203629446490 |
| Ad account "Edge Bourne Consulting" | 1025971549903293 (`act_1025971549903293`) |
| Dataset / pixel `edgebourne.com` | 1821497329119793 |
| Instant Form "EB \| Free intro call \| Higher intent" | 1132280359202136 |

---

## A. Create the app (about 5 min)

1. Go to <https://developers.facebook.com/apps> logged in as the Facebook account that
   admins the Edge Bourne business. If asked, register as a developer (accept the
   developer terms, verify with your phone).
2. **Create app**.
3. App details: name **Edge Bourne Ads Console**, contact email
   **eugene@edgebourne.com**.
4. Use cases: pick **Capture & manage ad leads with Marketing API** and
   **Create & manage ads with Marketing API** (Meta renames these from time to time;
   pick the lead-ads one and the Marketing API one). If Meta instead asks for an app type,
   choose **Business**.
5. Business portfolio: **Edge Bourne Consulting**.
6. Create the app (it re-asks for your Facebook password; that's you, not Claude).

## B. Basic settings (needed for Live mode)

App dashboard → **App settings → Basic**:

| Field | Value |
|---|---|
| Privacy policy URL | `https://edgebourne.com/privacy` |
| Terms of service URL | optional (`https://edgebourne.com`) |
| User data deletion | "Data deletion instructions URL": `https://edgebourne.com/privacy` |
| App icon | 1024×1024 PNG of the EB seal |
| Category | Business and pages |

Save. Then click **Show** next to **App secret** and copy **App ID** and **App secret**
into your password manager.

## C. Permissions

In each use case's **Customize / Permissions** screen, make sure these are added
(Standard/"Limited" access is enough because the app only touches your own business):

- `leads_retrieval`
- `pages_manage_metadata`, `pages_show_list`, `pages_read_engagement`, `pages_manage_ads`
- `pages_read_user_content` (the ad page's Comments tab reads the post's comments with it)
- `ads_management`, `ads_read`
- `business_management`
- `read_insights` (if offered)

No App Review is needed for your own assets. If Meta insists on review for
`leads_retrieval` once the app is Live, tell Claude: we'll prepare it.

## D. Switch the app to Live

Top of the app dashboard: **App mode → Live**. Meta's lead-ads docs: leads can't be
retrieved while the app is in Development mode. If the switch is blocked, it lists the
missing field from part B.

## E. System User and token (about 5 min)

1. <https://business.facebook.com/settings> → **Users → System users → Add**.
   Name **ads-console**, role **Admin** (it needs to manage the Page's lead subscription
   and the ad account).
2. **Assign assets** to ads-console:
   - Pages → Edge Bourne Consulting → **Full control** (covers ads + leads)
   - Ad accounts → Edge Bourne Consulting → **Full control** (manage campaigns)
   - Apps → Edge Bourne Ads Console → **Full control** (develop app)
   - Datasets → edgebourne.com (1821497329119793) → **Full control** (for Conversions API later)
3. **Generate new token**:
   - App: **Edge Bourne Ads Console**
   - Token expiration: **Never**
   - Permissions: tick everything from part C
   - Generate → copy it **once** into your password manager. Meta never shows it again.

## F. Leads access

Business settings → **Integrations → Leads access** → Edge Bourne Consulting Page.
If access is "customized/restricted", add **ads-console** (system user) and
**Edge Bourne Ads Console** (app). If it is still the default ("all admins"), nothing to do.

Also put the token in the local workspace for Claude's CLI (`meta-ads/.env`, gitignored):

```
ACCESS_TOKEN=<the system user token>
AD_ACCOUNT_ID=act_1025971549903293
BUSINESS_ID=2289619248494805
```

Check from Terminal: `meta auth status`.

## G. Connect the dashboard (after it is deployed)

1. DNS: an **A record** `ads` → your VPS IP (same as edgebourne.com).
2. On the VPS run the EdgeBourne installer and choose **2) Update**
   (`curl -fsSL https://raw.githubusercontent.com/ruolez/Edgebourne/main/install.sh | sudo bash`).
   It adds `ads.edgebourne.com` to the certificate once the DNS record resolves and prints the
   first sign-in password at the end.
3. Sign in at <https://ads.edgebourne.com> as eugene@edgebourne.com, set your own password.
4. **Settings → Meta**: App ID, App secret, System User token, and a **webhook verify token**
   (any long random string you invent, for example from a password manager). Save, then
   **Test connection**: it should name the System User, the Page and the ad account.
5. Meta app dashboard → **Webhooks** → object **Page** → **Subscribe to this object**:
   - Callback URL: `https://ads.edgebourne.com/webhooks/meta`
   - Verify token: the same one you typed in step 4
   - Verify and save, then subscribe to the **leadgen** field.
6. Dashboard **Settings → Meta → Start receiving leads** (installs the app on the Page:
   `POST /1404203629446490/subscribed_apps?subscribed_fields=leadgen`).
7. **Sync campaigns and recent leads** pulls the campaigns (for team assignment) and any leads
   from the last 30 days.
8. Test: <https://developers.facebook.com/tools/lead-ads-testing> → Page + form
   "EB | Free intro call | Higher intent" → **Create lead**. It appears in Leads (marked as a
   test) and in your inbox within a minute or two (Meta pings can lag a few minutes).

## H. Lead stages to Meta (about 10 min)

Once this is on, every lead you move to Contacted, Qualified, Won or Lost in the console is
reported to Meta, so Meta learns which people turn into clients. Test leads are never sent.
Screens in Meta move around; if a name below doesn't match, look for the nearest one.

1. **Give the system user the dataset.** business.facebook.com → Settings → Users → System
   users → the console's system user → **Assign assets** → **Datasets** (older screens:
   Pixels) → the Edge Bourne dataset (ID 1821497329119793) → turn on **Manage** → Save.
2. **Get a test code.** Events Manager → Data sources → that dataset → **Test events** tab.
   Copy the code it shows for server events (looks like `TEST12345`).
3. **Send a test.** Console → Settings → **Lead stages to Meta**: check the Dataset ID, paste
   the code under Test code, press **Send test event**. Within a minute a **Lead** event shows
   on the Test events tab. If the console says Meta refused it, the message says why (most
   often step 1 is missing).
4. **Switch it on.** Tick **Send lead stages to Meta** and press Save.
5. **Tell Meta what the stages mean** (after the first real stage change shows in the
   dataset's Overview): Events Manager → the dataset → Settings → the CRM / lead stages
   section → mark **Lead** as the first stage, **Contacted** and **Qualified** as the middle
   stages, **Won** as the converted stage. Lost needs no mapping.

What gets sent: the stage name, when it changed, and Meta's own id for the lead (the one the
form gave us). No names, phone numbers or emails. Meta accepts stages up to 7 days old, so
turning the switch on later still reports the last week's moves.

## Email (for lead alerts)

Nothing to set up if the website already sends email (website admin → **Email**): the ads
console uses those settings automatically, and Settings → Email shows which mailbox it uses.
**Send me a test email** checks it end to end. Enter a mailbox there only if ad alerts should
come from a different address.
