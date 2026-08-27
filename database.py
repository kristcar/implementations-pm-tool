import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "pm_tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate_db():
    """Run any pending schema migrations. Safe to call on every startup."""
    conn = get_db()
    c = conn.cursor()

    # Create version tracking table if it doesn't exist
    c.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        )
    """)
    row = c.execute("SELECT version FROM schema_version").fetchone()
    current = row["version"] if row else 0

    migrations = [
        # v1 — baseline schema (already exists for everyone, just stamp the version)
        None,
        # v2 — add risk_flag to projects
        "ALTER TABLE projects ADD COLUMN risk_flag INTEGER NOT NULL DEFAULT 0",
        # v3 — add project_notes table
        """CREATE TABLE IF NOT EXISTS project_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
        # v4 — add salesforce_link to projects
        "ALTER TABLE projects ADD COLUMN salesforce_link TEXT",
    ]

    for v, sql in enumerate(migrations, start=1):
        if current < v:
            if sql:
                try:
                    c.execute(sql)
                except Exception as e:
                    # Column may already exist on fresh installs via init_db
                    if "duplicate column name" not in str(e).lower():
                        raise
            current = v

    # Write final version back — insert if no row exists, update if one does
    if row:
        c.execute("UPDATE schema_version SET version = ?", (current,))
    else:
        c.execute("INSERT INTO schema_version (version) VALUES (?)", (current,))

    conn.commit()
    conn.close()


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            merchant_name TEXT,
            template_type TEXT NOT NULL DEFAULT 'standard',
            status TEXT NOT NULL DEFAULT 'active',
            ie_owner TEXT,
            platform TEXT,
            contract_start_date DATE,
            target_go_live_date DATE,
            actual_go_live_date DATE,
            notes TEXT,
            risk_flag INTEGER NOT NULL DEFAULT 0,
            salesforce_link TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS milestones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            target_date DATE,
            actual_date DATE,
            status TEXT NOT NULL DEFAULT 'upcoming',
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS task_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            task_group_id INTEGER REFERENCES task_groups(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT,
            owner TEXT DEFAULT 'ie',
            status TEXT NOT NULL DEFAULT 'not_started',
            due_date DATE,
            completed_at DATETIME,
            notes TEXT,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ie_owners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS project_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_type TEXT NOT NULL,
            group_name TEXT NOT NULL,
            task_title TEXT NOT NULL,
            task_description TEXT,
            owner TEXT DEFAULT 'ie',
            days_offset INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS project_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            author TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    _seed_templates(conn)
    conn.close()


def _seed_templates(conn):
    c = conn.cursor()
    # Always re-sync templates so code changes are reflected
    c.execute("DELETE FROM project_templates")

    # (group_name, title, description, owner, days_offset, sort_order)
    optimized_activation_tasks = [
        ("Kickoff and Confirm Scope", "🗓 Schedule Call & Confirm Project Details", "Schedule the kickoff call and confirm go-live target, scope, and key contacts.", "ie", 7, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "Engage advanced coding team if custom widget or theme work is in scope.", "ie", 0, 20),

        ("Recharge/Shopify Configuration", "Merchant - Download Recharge, Accept Billing Terms, Merchant Accepts Collab Access", "Merchant installs the ReCharge app, accepts billing terms, and grants collaborator access to the IE.", "merchant", 1, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "IE enables any Plus, Hybrid, or Custom features in the ReCharge dashboard and adds the store ID.", "ie", 1, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "Merchant reviews and confirms shipping, tax, and inventory settings are correct in ReCharge.", "merchant", 8, 30),

        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "Duplicate the live theme for development, create a test subscription plan, and preview the subscription widget.", "ie", 0, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "Set up bundle subscription offerings if applicable to this merchant's catalog.", "ie", 0, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "Configure any additional growth or retention features (e.g. cancel flows, loyalty, upsells).", "ie", 0, 30),

        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "Merchant completes a test purchase to generate a customer record in ReCharge for portal testing.", "merchant", 42, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "Configure customer portal settings (branding, actions, notifications) and verify end-to-end portal experience.", "ie", 21, 20),
        ("Configure Customer Experience", "Configure customer notifications", "Set up and test all customer-facing email and SMS notification flows.", "ie", 28, 30),

        ("Test & Go-Live", "Final Call & Sign Off", "Conduct final review call with merchant. Confirm all tasks are complete and obtain sign-off to go live.", "ie", 56, 10),
        ("Test & Go-Live", "Set the subscription widget live & configure plans on live products", "Switch the subscription widget from the test theme to the live theme and configure subscription plans on all live products.", "ie", 56, 20),

        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "If the merchant's Subscription Scorecard is below 50%, open a risk flag for the CSM team before transitioning.", "ie", 0, 10),
        ("Handoff", "Transition merchant to the next phase of support", "Complete the formal handoff to the CSM/support team with full project context.", "ie", 1, 20),
        ("Handoff", "Complete Customer Effort Score", "Submit the internal Customer Effort Score survey for this implementation.", "ie", 1, 30),
        ("Handoff", "Merchant - Congratulations!", "Send the merchant a congratulations message celebrating their go-live.", "ie", 0, 40),
    ]

    optimized_subscription_migration_tasks = [
        ("Kickoff and Confirm Scope", "🗓 Schedule Call & Confirm Project Details", "Schedule the kickoff call and confirm go-live target, migration tool (Migr8 or DMS), scope, and key contacts.", "ie", 9, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "Engage advanced coding team if custom widget or theme work is in scope for this migration.", "ie", 0, 20),

        ("Recharge/Shopify Configuration", "Merchant - Download Recharge & Accept Billing Terms", "Merchant installs the ReCharge app and accepts billing terms so the IE can begin configuration.", "merchant", 1, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "IE enables any Plus, Hybrid, or Custom features in the ReCharge dashboard, adds the store ID, and requests collaborator access.", "ie", 1, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "Merchant reviews and confirms shipping, tax, and inventory settings are correctly configured in ReCharge before migration proceeds.", "merchant", 10, 30),

        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "Duplicate the live theme for development, create a test subscription plan, and preview the subscription widget before migration.", "ie", 0, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "Set up bundle subscription offerings if applicable to this merchant's catalog.", "ie", 0, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "Configure any additional growth or retention features (e.g. cancel flows, loyalty, upsells) prior to migration.", "ie", 0, 30),

        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "Merchant completes a test purchase to generate a customer record in ReCharge for portal testing before going live.", "ie", 58, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "Configure customer portal settings (branding, actions, notifications) and verify end-to-end portal experience post-migration.", "ie", 29, 20),
        ("Configure Customer Experience", "Configure customer notifications", "Set up and test all customer-facing email and SMS notifications so migrated subscribers receive correct communications.", "ie", 38, 30),

        ("Complete a Test Migration", "For Migr8", "Run a test migration via Migr8 to validate data mapping and identify any errors before the live migration.", "ie", 2, 10),
        ("Complete a Test Migration", "For DMS: Create ZD Ticket, Pull Sub File, & Validate", "Open a ZD ticket with the DMS team, export the subscription file from the source platform, and validate it for errors.", "ie", 0, 20),
        ("Complete a Test Migration", "For DMS: Merchant - Review Validation Errors", "Merchant reviews any validation errors flagged in the test migration file and provides corrections or clarifications.", "merchant", 0, 30),
        ("Complete a Test Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "DMS team processes the validated test migration CSV and confirms completion so the merchant can verify data accuracy.", "ie", 0, 40),
        ("Complete a Test Migration", "For DMS: Merchant - Complete post-migration data check", "Merchant reviews migrated test data to confirm subscription records, billing dates, and customer details are correct.", "merchant", 0, 50),

        ("Test & Go-Live", "Final Call & Sign Off", "Conduct final review call with merchant to confirm all configuration and migration tasks are complete and obtain go-live sign-off.", "ie", 78, 10),
        ("Test & Go-Live", "Set the subscription widget live & configure plans on live products", "Switch the subscription widget to the live theme and configure subscription plans on all live products.", "ie", 78, 20),

        ("Complete the Live Migration", "For Migr8: Merchant - Review & resolve validation errors", "Merchant reviews and resolves any validation errors surfaced in the live Migr8 migration file before processing.", "merchant", 1, 10),
        ("Complete the Live Migration", "For Migr8: Recharge will process final migration CSV & confirm when complete", "Migr8 processes the live subscription CSV and confirms completion so the merchant can verify subscriber data.", "ie", 1, 20),
        ("Complete the Live Migration", "For Migr8: Merchant - Complete post-migration data check & uninstall previous app", "Merchant verifies all subscriber records migrated correctly and uninstalls the previous subscription app.", "merchant", 1, 30),
        ("Complete the Live Migration", "For Migr8: Review first processed charges for errors", "Review the first batch of charges processed by ReCharge post-migration to catch any billing errors early.", "ie", 0, 40),
        ("Complete the Live Migration", "For DMS: Create ZD Ticket, Place Charge Hold, Pull/Validate Sub File", "Open ZD ticket, place a charge hold to prevent double-billing, then pull and validate the live subscription file.", "ie", 0, 50),
        ("Complete the Live Migration", "For DMS: Merchant - Review & Resolve Validation Errors", "Merchant reviews and resolves any validation errors in the live subscription file before DMS processes it.", "merchant", 0, 60),
        ("Complete the Live Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "DMS team processes the live migration CSV and confirms completion so the merchant can perform a final data check.", "ie", 1, 70),
        ("Complete the Live Migration", "For DMS: Merchant - Complete post-migration data check & uninstall previous app", "Merchant confirms all subscriber records are accurate in ReCharge, then uninstalls the previous subscription platform.", "merchant", 1, 80),
        ("Complete the Live Migration", "For DMS: Review first processed charges for errors", "Review the first batch of charges processed by ReCharge post-migration to confirm billing accuracy.", "ie", 0, 90),

        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "If the merchant's Subscription Scorecard is below 50%, open a risk flag for the CSM team before transitioning.", "ie", 0, 10),
        ("Handoff", "Transition merchant to the next phase of support", "Complete the formal handoff to the CSM/support team with full project and migration context.", "ie", 1, 20),
        ("Handoff", "Merchant - Congratulations!", "Send the merchant a congratulations message celebrating their successful migration and go-live.", "ie", 0, 30),
    ]

    recharge_strategic_migration_tasks = [
        ("Kickoff and Confirm Scope", "🗓 Schedule Call & Confirm Project Details", "Schedule the kickoff call, align on strategic migration timeline, confirm go-live target, scope complexity, and key stakeholders.", "ie", 11, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "Engage advanced coding team early given the complexity of this strategic migration — custom theme or widget work may be needed.", "ie", 0, 20),

        ("Recharge/Shopify Configuration", "Merchant - Download Recharge & Accept Billing Terms", "Merchant installs the ReCharge app and accepts billing terms so the IE can begin configuring the platform.", "merchant", 1, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "IE enables Plus, Hybrid, or Custom features appropriate to this merchant's plan, adds the store ID, and requests collaborator access.", "ie", 1, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "Merchant reviews and confirms shipping, tax, and inventory settings are accurate in ReCharge before the extended build phase begins.", "merchant", 14, 30),

        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "Duplicate the live theme for development, create a test subscription plan, and preview the subscription widget ahead of migration.", "ie", 0, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "Set up bundle subscription offerings as part of this merchant's expanded subscription catalog.", "ie", 0, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "Configure growth and retention features (e.g. cancel flows, loyalty, upsells) that are part of this strategic scope.", "ie", 0, 30),

        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "Merchant completes a test purchase to generate a customer record in ReCharge, enabling portal and notification testing.", "ie", 80, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "Configure and test the customer portal thoroughly — branding, available actions, and notification flows — given the strategic scope.", "ie", 39, 20),
        ("Configure Customer Experience", "Configure customer notifications", "Set up and test all customer-facing email and SMS notifications to ensure migrated subscribers receive correct communications.", "ie", 52, 30),

        ("Complete a Test Migration", "For DMS: Create ZD Ticket, Pull Sub File, & Validate", "Open a ZD ticket with the DMS team, export the subscription file from the source platform, and validate it for errors.", "ie", 0, 10),
        ("Complete a Test Migration", "For DMS: Merchant - Review Validation Errors", "Merchant reviews validation errors flagged during the test migration and provides corrections before DMS proceeds.", "merchant", 0, 20),
        ("Complete a Test Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "DMS processes the validated test migration CSV and confirms completion for merchant review.", "ie", 0, 30),
        ("Complete a Test Migration", "For DMS: Merchant - Complete post-migration data check", "Merchant reviews migrated test data to confirm subscription records, billing dates, and customer details are accurate.", "merchant", 0, 40),

        ("Build/Testing & Go-Live", "Build/Testing", "Complete all custom build work and run full end-to-end testing across subscription flows, portal, and notifications before launch.", "ie", 108, 10),
        ("Build/Testing & Go-Live", "Go Live", "Execute the go-live plan — activate the subscription widget on the live theme and confirm all systems are functioning correctly.", "ie", 108, 20),

        ("Complete the Live Migration", "For DMS: Create ZD Ticket, Place Charge Hold, Pull/Validate Sub File", "Open ZD ticket, place a charge hold to prevent double-billing, then pull and validate the live subscription export.", "ie", 0, 10),
        ("Complete the Live Migration", "For DMS: Merchant - Review & Resolve Validation Errors", "Merchant reviews and resolves validation errors in the live subscription file before DMS processes the migration.", "merchant", 0, 20),
        ("Complete the Live Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "DMS processes the live migration CSV and confirms completion for merchant final verification.", "ie", 1, 30),
        ("Complete the Live Migration", "For DMS: Merchant - Complete post-migration data check & uninstall previous app", "Merchant confirms all subscriber records are accurate in ReCharge, then uninstalls the legacy subscription platform.", "merchant", 1, 40),
        ("Complete the Live Migration", "For DMS: Review first processed charges for errors", "Review the first batch of charges processed by ReCharge post-migration to confirm billing accuracy and catch any issues early.", "ie", 0, 50),

        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "If the Subscription Scorecard is below 50%, open a risk flag for the CSM team before handoff given the strategic account complexity.", "ie", 0, 10),
        ("Handoff", "Transition merchant to CSM", "Complete the formal handoff to the CSM team with full project, migration, and strategic context documented.", "ie", 1, 20),
        ("Handoff", "Merchant - Congratulations!", "Send the merchant a congratulations message celebrating the completion of their strategic migration and go-live.", "ie", 0, 30),
    ]

    skio_tasks = [
        # Group 1: Kickoff — ~0–18% of timeline (natural span: 17 days)
        # days_offset = gap from this task to the next
        ("Kickoff", "Migration checklist sent to merchant", "", "ie", 2, 10),
        ("Kickoff", "Migration checklist completed by Merchant", "", "merchant", 3, 20),
        ("Kickoff", "Migration Onboarding Form completed by Merchant", "", "merchant", 1, 30),
        ("Kickoff", "Send Launch Intro", "", "ie", 1, 40),
        ("Kickoff", "Skio App installed", "", "ie", 2, 50),
        ("Kickoff", "Set Customers Skio Instance to isPaying = true AND add Stripe ID", "", "ie", 1, 60),
        ("Kickoff", "Check Take Rate", "", "ie", 1, 70),
        ("Kickoff", "Cancel Merchant Trials and Shopify Billing", "", "ie", 2, 80),
        ("Kickoff", "Collaborator access accepted by Merchant", "", "merchant", 4, 90),

        # Group 2: Theme & Integration — ~18–73% of timeline (natural span: 57 days)
        ("Theme & Integration", "Send Intro Email", "", "ie", 2, 10),
        ("Theme & Integration", "Review Onboarding Form", "", "ie", 1, 20),
        ("Theme & Integration", "Check Problem Apps", "", "ie", 1, 30),
        ("Theme & Integration", "Review Current Subscription Setup", "", "ie", 2, 40),
        ("Theme & Integration", "Check theme codebase for reference to \"selling_plan\" to ensure creating in Skio won't affect the frontend", "Search the theme code for existing selling_plan references to avoid breaking the storefront when Skio selling plans are created.", "ie", 3, 50),
        ("Theme & Integration", "Create Filter theme (if needed)", "", "ie", 5, 60),
        ("Theme & Integration", "Send Filter theme to merchant for approval", "", "ie", 4, 70),
        ("Theme & Integration", "Publish Filter theme", "", "ie", 1, 80),
        ("Theme & Integration", "Check Problem apps before generating selling plans", "", "ie", 2, 90),
        ("Theme & Integration", "Create Selling Plans in Skio Dashboard", "", "ie", 3, 100),
        ("Theme & Integration", "Skio Plan Picker has been integrated on Product Pages", "", "ie", 3, 110),
        ("Theme & Integration", "Make sure that Variant switching works with subscriptions on the PDP", "", "ie", 2, 120),
        ("Theme & Integration", "Integrate Subscription Functionality Into Cart (if applicable)", "", "ie", 3, 130),
        ("Theme & Integration", "Setup Skio Login as indicated in Onboarding Form", "", "ie", 2, 140),
        ("Theme & Integration", "Replicate other subscription functionality on site", "", "ie", 4, 150),
        ("Theme & Integration", "Ensure Shipping rates / Journeys / Volume Discounts / Surprise & Delight have been setup", "", "ie", 3, 160),
        ("Theme & Integration", "Review current workflows / automations that \"update\" a subscription", "Audit any existing Shopify Flow or third-party automations that modify subscriptions to ensure they are compatible with Skio.", "ie", 2, 170),
        ("Theme & Integration", "Shipping Rules (Match Parity)", "", "ie", 2, 180),
        ("Theme & Integration", "Theme preview sent to the Merchant", "", "ie", 4, 190),
        ("Theme & Integration", "Skio Theme Published", "", "ie", 3, 200),
        ("Theme & Integration", "Create Migration Handoff comment", "", "ie", 4, 210),

        # Group 3: Migration — ~73–100% of timeline (natural span: 20 days)
        # Last task has offset=0 so it lands exactly on go-live date
        ("Migration", "Check for complicated data migration scenarios", "", "ie", 2, 10),
        ("Migration", "Send Migration Intro Email", "", "ie", 2, 20),
        ("Migration", "Request Customer to Input API Keys / Connect Payment Provider", "", "merchant", 4, 30),
        ("Migration", "Generate and Send Migration Preview to Merchant", "", "ie", 3, 40),
        ("Migration", "Ensure previous platform is done billing for the day", "", "ie", 3, 50),
        ("Migration", "Perform Data Migration and Verify Data", "", "ie", 1, 60),
        ("Migration", "Add Manage Subscription Link or Replace Login", "", "ie", 1, 70),
        ("Migration", "Redirect Previous Customer Portal", "", "ie", 1, 80),
        ("Migration", "Cancel or Delete Previous Subscription App", "", "ie", 1, 90),
        ("Migration", "Delete Previous App selling plans", "", "ie", 1, 100),
        ("Migration", "Set billMigratedSubs to true in the /skioadmin page", "", "ie", 1, 110),
        ("Migration", "Migration Complete", "", "ie", 0, 120),
    ]

    store_optimization_tasks = [
        # Group 1: Kickoff and Confirm Scope
        ("Kickoff and Confirm Scope", "🗓 Schedule call and Review / Confirm Project details", "Schedule the kickoff call and confirm which store optimization features are in scope and the target completion timeline.", "ie", 2, 10),
        ("Kickoff and Confirm Scope", "Approve Scoping & Project Plan", "Merchant reviews and approves the scoping document and project plan before optimization work begins.", "merchant", 1, 20),

        # Group 2: Configure Failed Payment Recovery
        ("Configure Failed Payment Recovery", "Configure Failed Payment Recovery", "Set up failed payment recovery flows (dunning sequences) to automatically retry and recover failed subscription charges.", "merchant", 1, 10),
        ("Configure Failed Payment Recovery", "Enable Frictionless Payment Updates", "Enable frictionless payment update flows so subscribers can update their payment method without contacting support.", "merchant", 0, 20),

        # Group 3: Configure Referrals
        ("Configure Referrals", "Configure the \"Incentivize Friends\" Flow", "Set up the referral flow that incentivizes existing subscribers to refer friends with a discount or reward.", "merchant", 1, 10),
        ("Configure Referrals", "Configure the \"Reward Advocates\" Flow", "Configure the advocate reward flow that automatically rewards subscribers when their referral converts.", "merchant", 1, 20),
        ("Configure Referrals", "(Optional): Refer Friends After Checkout", "Optionally configure a post-checkout referral prompt to encourage newly converted subscribers to refer friends.", "merchant", 0, 30),
        ("Configure Referrals", "(Optional): Send Reminder to Refer Friends", "Optionally set up a reminder notification to re-engage subscribers who haven't yet used their referral link.", "merchant", 0, 40),

        # Group 4: Configure Rewards
        ("Configure Rewards", "Cash-back credits talking points", "IE reviews cash-back credit talking points with the merchant to align on how to position rewards to their subscribers.", "ie", 0, 10),
        ("Configure Rewards", "Additional Reward strategies", "IE presents additional reward strategies the merchant can layer on top of cash-back credits to drive retention.", "ie", 0, 20),
        ("Configure Rewards", "Build Rewards: Cash-back Credits Experience", "Merchant builds the cash-back credits rewards experience in ReCharge, configuring earn rates and redemption rules.", "merchant", 1, 30),
        ("Configure Rewards", "Review Credit settings", "Merchant reviews credit settings to confirm earn rates, expiration rules, and redemption thresholds are correct.", "merchant", 1, 40),
        ("Configure Rewards", "Review Credit translations", "Merchant reviews and updates credit-related copy and translations to match their brand voice.", "merchant", 1, 50),
        ("Configure Rewards", "Activate Rewards flow", "Merchant activates the rewards flow to make cash-back credits visible and redeemable for subscribers.", "merchant", 1, 60),

        # Group 5: Configure Cancellation Prevention
        ("Configure Cancellation Prevention", "Configure Cancellation Prevention", "Set up cancellation prevention flows (e.g. pause, skip, swap, discount offers) to reduce voluntary churn.", "merchant", 2, 10),

        # Group 6: Bundles
        ("Bundles", "Review Bundle Use Cases and Determine Your Bundle Type", "Review the merchant's product catalog and goals to determine the right bundle type: preset, customizable, or dynamic.", "ie", 0, 10),
        ("Bundles", "Configure Preset and/or Customizable Bundles", "Configure preset or customizable bundle products in ReCharge to allow subscribers to subscribe to curated product sets.", "ie", 0, 20),
        ("Bundles", "Configure Dynamic Bundles", "Set up dynamic bundles so subscribers can build their own bundle from a defined product collection.", "ie", 0, 30),
        ("Bundles", "Review Inventory Management for Bundle Collections", "Review how inventory will be tracked and managed for bundle collection products to prevent overselling.", "ie", 0, 40),
        ("Bundles", "Configure an Out-Of-Stock Klaviyo Campaign for Bundle Contents", "Set up a Klaviyo campaign to notify subscribers when a bundle component goes out of stock.", "ie", 0, 50),

        # Group 7: Concierge SMS
        ("Concierge SMS", "Configure Concierge SMS", "Configure Concierge SMS to enable two-way SMS communication between subscribers and the merchant's support team.", "ie", 1, 10),
        ("Concierge SMS", "Confirm Phone Number Approval", "Confirm that the merchant's SMS phone number has been approved and is ready for subscriber-facing communication.", "ie", 5, 20),

        # Group 8: Custom Widget
        ("Custom Widget", "Create a custom widget", "Build a custom subscription widget tailored to the merchant's theme and UX requirements.", "ie", 0, 10),

        # Group 9: Revenue Growth Feature Activation
        ("Revenue Growth Feature Activation", "Recharge Cart + Cart Overlay", "Configure the ReCharge cart and cart overlay to surface subscription upsell opportunities during the shopping experience.", "ie", 0, 10),
        ("Revenue Growth Feature Activation", "Set up Post-Purchase Cross-Sell", "Set up a post-purchase cross-sell to offer complementary subscription products to customers after checkout.", "ie", 0, 20),
        ("Revenue Growth Feature Activation", "Set up Checkout Cross-sell", "Configure a checkout cross-sell to surface subscription add-ons or upgrades at the point of purchase.", "ie", 0, 30),

        # Group 10: Automate
        ("Automate", "Build Automate experiences", "Build Automate experiences (e.g. win-back, upsell, loyalty triggers) to drive revenue and retention through automated subscriber journeys.", "ie", 0, 10),

        # Group 11: Configure Gift Subscriptions
        ("Configure Gift Subscriptions", "Set up Gift Subscriptions", "Configure gift subscription products so customers can purchase subscriptions as gifts for others.", "ie", 0, 10),

        # Group 12: Legacy Subscription Widget
        ("Legacy Subscription Widget", "Set up Recharge subscription widget", "Install and configure the legacy ReCharge subscription widget on product pages to enable subscribe & save.", "ie", 0, 10),
        ("Legacy Subscription Widget", "Set Subscription as the Default Option - Recommended", "Configure the widget so the subscription option is selected by default, increasing subscribe & save conversion rates.", "ie", 0, 20),
        ("Legacy Subscription Widget", "Preview the Subscription Widget", "Preview the subscription widget on a test product to confirm it displays and functions correctly before going live.", "ie", 0, 30),

        # Group 13: Handoff
        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "If the merchant's Subscription Scorecard is below 50%, open a risk flag for the CSM team before transitioning.", "ie", 0, 10),
        ("Handoff", "Transition merchant to the next phase of support", "Complete the formal handoff to the CSM/support team with full context on the store optimization work completed.", "ie", 1, 20),
        ("Handoff", "Complete Customer Effort Score", "Submit the internal Customer Effort Score survey for this store optimization engagement.", "merchant", 1, 30),
        ("Handoff", "Congratulations! You've Completed Recharge Implementation", "Send the merchant a congratulations message celebrating the completion of their store optimization project.", "ie", 0, 40),
    ]

    template_map = {
        "optimized_activation": optimized_activation_tasks,
        "optimized_subscription_migration": optimized_subscription_migration_tasks,
        "recharge_strategic_migration": recharge_strategic_migration_tasks,
        "skio": skio_tasks,
        "store_optimization": store_optimization_tasks,
    }

    for tpl_type, rows in template_map.items():
        for row in rows:
            c.execute(
                "INSERT INTO project_templates (template_type, group_name, task_title, task_description, owner, days_offset, sort_order) VALUES (?,?,?,?,?,?,?)",
                (tpl_type,) + row,
            )

    conn.commit()
