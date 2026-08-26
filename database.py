import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "pm_tool.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
        ("Handoff", "Merchant - Congratulations!", "Send the merchant a congratulations message celebrating their go-live.", "merchant", 0, 40),
    ]

    optimized_subscription_migration_tasks = [
        ("Kickoff and Confirm Scope", "🗓 Schedule Call & Confirm Project Details", "", "ie", 9, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "", "ie", 0, 20),

        ("Recharge/Shopify Configuration", "Merchant - Download Recharge & Accept Billing Terms", "", "merchant", 1, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "", "ie", 1, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "", "merchant", 10, 30),

        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "", "ie", 0, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "", "ie", 0, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "", "ie", 0, 30),

        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "", "ie", 58, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "", "ie", 29, 20),
        ("Configure Customer Experience", "Configure customer notifications", "", "ie", 38, 30),

        ("Complete a Test Migration", "For Migr8", "", "ie", 2, 10),
        ("Complete a Test Migration", "For DMS: Create ZD Ticket, Pull Sub File, & Validate", "", "ie", 0, 20),
        ("Complete a Test Migration", "For DMS: Merchant - Review Validation Errors", "", "merchant", 0, 30),
        ("Complete a Test Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "", "ie", 0, 40),
        ("Complete a Test Migration", "For DMS: Merchant - Complete post-migration data check", "", "merchant", 0, 50),

        ("Test & Go-Live", "Final Call & Sign Off", "", "ie", 78, 10),
        ("Test & Go-Live", "Set the subscription widget live & configure plans on live products", "", "ie", 78, 20),

        ("Complete the Live Migration", "For Migr8: Merchant - Review & resolve validation errors", "", "merchant", 1, 10),
        ("Complete the Live Migration", "For Migr8: Recharge will process final migration CSV & confirm when complete", "", "ie", 1, 20),
        ("Complete the Live Migration", "For Migr8: Merchant - Complete post-migration data check & uninstall previous app", "", "merchant", 1, 30),
        ("Complete the Live Migration", "For Migr8: Review first processed charges for errors", "", "ie", 0, 40),
        ("Complete the Live Migration", "For DMS: Create ZD Ticket, Place Charge Hold, Pull/Validate Sub File", "", "ie", 0, 50),
        ("Complete the Live Migration", "For DMS: Merchant - Review & Resolve Validation Errors", "", "merchant", 0, 60),
        ("Complete the Live Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "", "ie", 1, 70),
        ("Complete the Live Migration", "For DMS: Merchant - Complete post-migration data check & uninstall previous app", "", "merchant", 1, 80),
        ("Complete the Live Migration", "For DMS: Review first processed charges for errors", "", "ie", 0, 90),

        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "", "ie", 0, 10),
        ("Handoff", "Transition merchant to the next phase of support", "", "ie", 1, 20),
        ("Handoff", "Merchant - Congratulations!", "", "merchant", 0, 30),
    ]

    recharge_strategic_migration_tasks = [
        ("Kickoff and Confirm Scope", "🗓 Schedule Call & Confirm Project Details", "", "ie", 11, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "", "ie", 0, 20),

        ("Recharge/Shopify Configuration", "Merchant - Download Recharge & Accept Billing Terms", "", "merchant", 1, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "", "ie", 1, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "", "merchant", 14, 30),

        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "", "ie", 0, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "", "ie", 0, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "", "ie", 0, 30),

        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "", "ie", 80, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "", "ie", 39, 20),
        ("Configure Customer Experience", "Configure customer notifications", "", "ie", 52, 30),

        ("Complete a Test Migration", "For DMS: Create ZD Ticket, Pull Sub File, & Validate", "", "ie", 0, 10),
        ("Complete a Test Migration", "For DMS: Merchant - Review Validation Errors", "", "merchant", 0, 20),
        ("Complete a Test Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "", "ie", 0, 30),
        ("Complete a Test Migration", "For DMS: Merchant - Complete post-migration data check", "", "merchant", 0, 40),

        ("Build/Testing & Go-Live", "Build/Testing", "", "ie", 108, 10),
        ("Build/Testing & Go-Live", "Go Live", "", "ie", 108, 20),

        ("Complete the Live Migration", "For DMS: Create ZD Ticket, Place Charge Hold, Pull/Validate Sub File", "", "ie", 0, 10),
        ("Complete the Live Migration", "For DMS: Merchant - Review & Resolve Validation Errors", "", "merchant", 0, 20),
        ("Complete the Live Migration", "For DMS: Recharge will process final migration CSV & confirm when complete", "", "ie", 1, 30),
        ("Complete the Live Migration", "For DMS: Merchant - Complete post-migration data check & uninstall previous app", "", "merchant", 1, 40),
        ("Complete the Live Migration", "For DMS: Review first processed charges for errors", "", "ie", 0, 50),

        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "", "ie", 0, 10),
        ("Handoff", "Transition merchant to CSM", "", "ie", 1, 20),
        ("Handoff", "Merchant - Congratulations!", "", "merchant", 0, 30),
    ]

    skio_tasks = [
        # Group 1: Kickoff
        ("Kickoff", "Migration checklist sent to merchant", "", "ie", 0, 10),
        ("Kickoff", "Migration checklist completed by Merchant", "", "merchant", 0, 20),
        ("Kickoff", "Migration Onboarding Form completed by Merchant", "", "merchant", 0, 30),
        ("Kickoff", "Send Launch Intro", "", "ie", 0, 40),
        ("Kickoff", "Skio App installed", "", "ie", 0, 50),
        ("Kickoff", "Set Customers Skio Instance to isPaying = true AND add Stripe ID", "", "ie", 0, 60),
        ("Kickoff", "Check Take Rate", "", "ie", 0, 70),
        ("Kickoff", "Cancel Merchant Trials and Shopify Billing", "", "ie", 0, 80),
        ("Kickoff", "Collaborator access accepted by Merchant", "", "merchant", 0, 90),

        # Group 2: Theme & Integration
        ("Theme & Integration", "Send Intro Email", "", "ie", 0, 10),
        ("Theme & Integration", "Review Onboarding Form", "", "ie", 0, 20),
        ("Theme & Integration", "Check Problem Apps", "", "ie", 0, 30),
        ("Theme & Integration", "Review Current Subscription Setup", "", "ie", 0, 40),
        ("Theme & Integration", "Check theme codebase for reference to \"selling_plan\" to ensure creating in Skio won't affect the frontend", "", "ie", 0, 50),
        ("Theme & Integration", "Create Filter theme (if needed)", "", "ie", 0, 60),
        ("Theme & Integration", "Send Filter theme to merchant for approval", "", "ie", 0, 70),
        ("Theme & Integration", "Publish Filter theme", "", "ie", 0, 80),
        ("Theme & Integration", "Check Problem apps before generating selling plans", "", "ie", 0, 90),
        ("Theme & Integration", "Create Selling Plans in Skio Dashboard", "", "ie", 0, 100),
        ("Theme & Integration", "Skio Plan Picker has been integrated on Product Pages", "", "ie", 0, 110),
        ("Theme & Integration", "Make sure that Variant switching works with subscriptions on the PDP", "", "ie", 0, 120),
        ("Theme & Integration", "Integrate Subscription Functionality Into Cart (if applicable)", "", "ie", 0, 130),
        ("Theme & Integration", "Setup Skio Login as indicated in Onboarding Form", "", "ie", 0, 140),
        ("Theme & Integration", "Replicate other subscription functionality on site", "", "ie", 0, 150),
        ("Theme & Integration", "Ensure Shipping rates / Journeys / Volume Discounts / Surprise & Delight have been setup", "", "ie", 0, 160),
        ("Theme & Integration", "Review current workflows / automations that \"update\" a subscription", "", "ie", 0, 170),
        ("Theme & Integration", "Shipping Rules (Match Parity)", "", "ie", 0, 180),
        ("Theme & Integration", "Theme preview sent to the Merchant", "", "ie", 0, 190),
        ("Theme & Integration", "Skio Theme Published", "", "ie", 0, 200),
        ("Theme & Integration", "Create Migration Handoff comment", "", "ie", 0, 210),

        # Group 3: Migration
        ("Migration", "Check for complicated data migration scenarios", "", "ie", 0, 10),
        ("Migration", "Send Migration Intro Email", "", "ie", 0, 20),
        ("Migration", "Request Customer to Input API Keys / Connect Payment Provider", "", "merchant", 0, 30),
        ("Migration", "Generate and Send Migration Preview to Merchant", "", "ie", 0, 40),
        ("Migration", "Ensure previous platform is done billing for the day", "", "ie", 0, 50),
        ("Migration", "Perform Data Migration and Verify Data", "", "ie", 0, 60),
        ("Migration", "Add Manage Subscription Link or Replace Login", "", "ie", 0, 70),
        ("Migration", "Redirect Previous Customer Portal", "", "ie", 0, 80),
        ("Migration", "Cancel or Delete Previous Subscription App", "", "ie", 0, 90),
        ("Migration", "Delete Previous App selling plans", "", "ie", 0, 100),
        ("Migration", "Set billMigratedSubs to true in the /skioadmin page", "", "ie", 0, 110),
        ("Migration", "Migration Complete", "", "ie", 0, 120),
    ]

    store_optimization_tasks = [
        # Group 1: Kickoff and Confirm Scope
        ("Kickoff and Confirm Scope", "🗓 Schedule call and Review / Confirm Project details", "", "ie", 2, 10),
        ("Kickoff and Confirm Scope", "Approve Scoping & Project Plan", "", "merchant", 1, 20),

        # Group 2: Retain Setup
        ("Retain Setup", "Configure Failed Payment Recovery", "", "merchant", 1, 10),
        ("Retain Setup", "Enable Frictionless Payment Updates", "", "merchant", 0, 20),
        ("Retain Setup", "Configure the \"Incentivize Friends\" Flow", "", "merchant", 1, 30),
        ("Retain Setup", "Configure the \"Reward Advocates\" Flow", "", "merchant", 1, 40),
        ("Retain Setup", "(Optional): Refer Friends After Checkout", "", "merchant", 0, 50),
        ("Retain Setup", "(Optional): Send Reminder to Refer Friends", "", "merchant", 0, 60),
        ("Retain Setup", "Configure Rewards", "", "merchant", 4, 70),
        ("Retain Setup", "Cash-back credits talking points", "", "ie", 0, 80),
        ("Retain Setup", "Additional Reward strategies", "", "ie", 0, 90),
        ("Retain Setup", "Build Rewards: Cash-back Credits Experience", "", "merchant", 1, 100),
        ("Retain Setup", "Review Credit settings", "", "merchant", 1, 110),
        ("Retain Setup", "Review Credit translations", "", "merchant", 1, 120),
        ("Retain Setup", "Activate Rewards flow", "", "merchant", 1, 130),
        ("Retain Setup", "Configure Cancellation Prevention", "", "merchant", 2, 140),
        ("Retain Setup", "Complete Cancellation Prevention setup", "", "merchant", 1, 150),

        # Group 3: Handoff
        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "", "ie", 0, 20),
        ("Handoff", "Transition merchant to the next phase of support", "", "ie", 1, 30),
        ("Handoff", "Complete Customer Effort Score", "", "merchant", 1, 40),
        ("Handoff", "Congratulations! You've Completed Recharge Implementation", "", "merchant", 0, 50),
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
