import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "pm_tool.db")


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
    c.execute("SELECT COUNT(*) FROM project_templates")
    if c.fetchone()[0] > 0:
        return

    standard_tasks = [
        # (group_name, title, description, owner, days_offset, sort_order)
        # Source: GuideCX "Optimized Activation - Final" template

        # Milestone 1 — Kickoff and Confirm Scope
        ("Kickoff and Confirm Scope", "Schedule Call & Confirm Project Details", "Schedule the kickoff call and confirm go-live target, scope, and key contacts.", "ie", 3, 10),
        ("Kickoff and Confirm Scope", "Advanced Coding Services, if applicable", "Engage advanced coding team if custom widget or theme work is in scope.", "ie", 5, 20),

        # Milestone 2 — Recharge/Shopify Configuration
        ("Recharge/Shopify Configuration", "Merchant - Download Recharge, Accept Billing Terms, Merchant Accepts Collab Access", "Merchant installs the ReCharge app, accepts billing terms, and grants collaborator access to the IE.", "merchant", 7, 10),
        ("Recharge/Shopify Configuration", "Enable Plus/Hybrid/Custom Features, Add Store ID, Request Collab Access", "IE enables any Plus, Hybrid, or Custom features in the ReCharge dashboard and adds the store ID.", "ie", 7, 20),
        ("Recharge/Shopify Configuration", "Merchant - Review your Settings - Shipping, Taxes and Inventory", "Merchant reviews and confirms shipping, tax, and inventory settings are correct in ReCharge.", "merchant", 14, 30),

        # Milestone 3 — Configure Subscription Checkout Flow
        ("Configure Subscription Checkout Flow", "Duplicate Theme, Create Product Subscription Plan for Testing, & Preview Widget", "Duplicate the live theme for development, create a test subscription plan, and preview the subscription widget.", "ie", 14, 10),
        ("Configure Subscription Checkout Flow", "Configure Bundles", "Set up bundle subscription offerings if applicable to this merchant's catalog.", "ie", 21, 20),
        ("Configure Subscription Checkout Flow", "Additional Growth & Retention Features", "Configure any additional growth or retention features (e.g. cancel flows, loyalty, upsells).", "ie", 21, 30),

        # Milestone 4 — Configure Customer Experience
        ("Configure Customer Experience", "Merchant - Run Test Transaction to Create Customer Record", "Merchant completes a test purchase to generate a customer record in ReCharge for portal testing.", "merchant", 28, 10),
        ("Configure Customer Experience", "Adjust customer portal settings & test portal", "Configure customer portal settings (branding, actions, notifications) and verify end-to-end portal experience.", "ie", 35, 20),
        ("Configure Customer Experience", "Configure customer notifications", "Set up and test all customer-facing email and SMS notification flows.", "ie", 35, 30),

        # Milestone 5 — Test & Go-Live
        ("Test & Go-Live", "Final Call & Sign Off", "Conduct final review call with merchant. Confirm all tasks are complete and obtain sign-off to go live.", "ie", 49, 10),
        ("Test & Go-Live", "Set the subscription widget live & configure plans on live products", "Switch the subscription widget from the test theme to the live theme and configure subscription plans on all live products.", "ie", 56, 20),

        # Milestone 6 — Handoff
        ("Handoff", "Open Risk if Subscription Scorecard is <50%", "If the merchant's Subscription Scorecard is below 50%, open a risk flag for the CSM team before transitioning.", "ie", 57, 10),
        ("Handoff", "Transition merchant to the next phase of support", "Complete the formal handoff to the CSM/support team with full project context.", "ie", 58, 20),
        ("Handoff", "Complete Customer Effort Score", "Submit the internal Customer Effort Score survey for this implementation.", "ie", 58, 30),
        ("Handoff", "Merchant - Congratulations!", "Send the merchant a congratulations message celebrating their go-live.", "merchant", 58, 40),
    ]

    enterprise_tasks = [
        # Phase 1 — Pre-Kickoff
        ("Pre-Kickoff", "Internal handoff call with Sales and Solutions Engineering", "Review sold scope and any custom commitments.", "ie", 1, 10),
        ("Pre-Kickoff", "Review contract scope and custom commitments", "Document all contractual obligations.", "ie", 2, 20),
        ("Pre-Kickoff", "Build stakeholder map", "Identify all merchant contacts and their roles.", "ie", 3, 30),
        ("Pre-Kickoff", "Draft project plan and share with merchant", "Create detailed project schedule.", "ie", 5, 40),
        ("Pre-Kickoff", "Review and approve project plan", "Merchant confirms timeline and milestones.", "merchant", 10, 50),
        ("Pre-Kickoff", "Provision sandbox and staging environment", "Set up dedicated staging instance.", "ie", 7, 60),
        ("Pre-Kickoff", "Complete technical questionnaire", "Collect platform, ERP, WMS, and 3PL details.", "merchant", 10, 70),
        ("Pre-Kickoff", "Schedule kickoff with all stakeholders", "Coordinate across all merchant departments.", "ie", 7, 80),
        # Phase 2 — Discovery & Solution Design
        ("Discovery & Solution Design", "Lead kickoff call — all stakeholders", "Full team introductions and project overview.", "ie", 14, 10),
        ("Discovery & Solution Design", "Conduct technical discovery session", "Deep dive into platform and integration architecture.", "ie", 17, 20),
        ("Discovery & Solution Design", "Conduct business and merchandising discovery session", "Understand subscription strategy and product catalog.", "ie", 19, 30),
        ("Discovery & Solution Design", "Document full current-state subscription workflow", "Map existing process from purchase to renewal.", "ie", 22, 40),
        ("Discovery & Solution Design", "Map data migration requirements", "Identify subscribers, orders, and payment methods to migrate.", "ie", 24, 50),
        ("Discovery & Solution Design", "Provide data export from legacy platform", "Export all subscriber and order data.", "merchant", 28, 60),
        ("Discovery & Solution Design", "Draft Solution Design Document (SDD)", "Formal technical specification for the implementation.", "ie", 30, 70),
        ("Discovery & Solution Design", "Present SDD to merchant for approval", "Walkthrough and Q&A session.", "ie", 32, 80),
        ("Discovery & Solution Design", "Sign off on SDD", "Formal written approval of solution design.", "merchant", 35, 90),
        # Phase 3 — Data Migration Planning
        ("Data Migration", "Map legacy subscriber data schema to ReCharge schema", "Field-level mapping document.", "ie", 37, 10),
        ("Data Migration", "Run data audit on provided export", "Check for nulls, duplicates, and anomalies.", "ie", 40, 20),
        ("Data Migration", "Write and test migration script in sandbox", "Build and validate migration tooling.", "ie", 45, 30),
        ("Data Migration", "Validate sample migration records", "Merchant spot-checks a sample of migrated data.", "merchant", 48, 40),
        ("Data Migration", "Finalize migration runbook", "Document all steps, validation checks, and rollback plan.", "ie", 50, 50),
        # Phase 4 — Configuration
        ("Configuration", "Install ReCharge on staging storefront", "Platform installation in staging environment.", "ie", 36, 10),
        ("Configuration", "Configure subscription products — all SKUs and intervals", "Full catalog setup with all billing frequencies.", "ie", 42, 20),
        ("Configuration", "Build custom customer portal", "Custom portal development if in scope.", "ie", 55, 30),
        ("Configuration", "Configure multi-currency and multi-region", "Set up regional pricing and currencies if applicable.", "ie", 55, 40),
        ("Configuration", "Configure ERP integration", "Webhook mapping for order sync to ERP.", "ie", 60, 50),
        ("Configuration", "Configure WMS and 3PL integration", "Connect fulfillment and inventory systems.", "ie", 65, 60),
        ("Configuration", "Configure ESP integration and transactional email flows", "Set up all triggered email communications.", "ie", 50, 70),
        ("Configuration", "Configure loyalty program integration", "Connect loyalty platform if applicable.", "ie", 55, 80),
        ("Configuration", "Configure bundles, prepaid, and gift subscriptions", "Set up advanced subscription types if in scope.", "ie", 65, 90),
        ("Configuration", "Configure dunning, retry logic, and payment failure flows", "Define full payment recovery strategy.", "ie", 70, 100),
        ("Configuration", "Set up analytics and reporting dashboards", "Configure all reporting and attribution.", "ie", 75, 110),
        ("Configuration", "Review configuration in staging", "Merchant reviews all configuration before UAT.", "merchant", 78, 120),
        # Phase 5 — Integration Testing
        ("Integration Testing", "End-to-end integration test: order to ERP to WMS", "Full order flow validation across systems.", "ie", 82, 10),
        ("Integration Testing", "Payment processing stress test", "Test payment flows at volume.", "ie", 84, 20),
        ("Integration Testing", "Multi-storefront sync test", "Verify data consistency across storefronts if applicable.", "ie", 86, 30),
        ("Integration Testing", "Regression test all subscription flows", "Full regression across all subscription types.", "ie", 90, 40),
        ("Integration Testing", "Performance and load test customer portal", "Validate portal performance under load.", "ie", 92, 50),
        ("Integration Testing", "Lead UAT with internal team", "Merchant-led user acceptance testing.", "merchant", 96, 60),
        ("Integration Testing", "Submit UAT findings", "Document all issues found during UAT.", "merchant", 98, 70),
        ("Integration Testing", "Resolve UAT issues", "Fix all merchant-reported issues.", "ie", 100, 80),
        ("Integration Testing", "Final UAT sign-off", "Written approval that UAT is complete.", "merchant", 100, 90),
        # Phase 6 — Migration Execution
        ("Migration Execution", "Final data export from legacy platform", "Pull latest subscriber and order data.", "merchant", 102, 10),
        ("Migration Execution", "Run migration to production environment", "Execute migration script against production.", "ie", 110, 20),
        ("Migration Execution", "Validate migrated subscriber records", "IE verifies record counts and spot-checks data.", "ie", 112, 30),
        ("Migration Execution", "Spot-check migrated customer accounts", "Merchant validates their own subscriber data.", "merchant", 114, 40),
        ("Migration Execution", "Freeze legacy platform", "Coordinate cutover and disable legacy subscriptions.", "merchant", 115, 50),
        # Phase 7 — Go-Live Preparation
        ("Go-Live Preparation", "Final production pre-launch checklist", "Review every item before go-live.", "ie", 116, 10),
        ("Go-Live Preparation", "Confirm rollback plan and criteria", "Document when and how to roll back if needed.", "ie", 117, 20),
        ("Go-Live Preparation", "Internal team training session", "Train merchant staff on the new platform.", "merchant", 118, 30),
        ("Go-Live Preparation", "Prepare merchant launch day runbook", "Step-by-step guide for merchant team on launch day.", "ie", 120, 40),
        ("Go-Live Preparation", "Approve go-live readiness", "Formal merchant sign-off before launch.", "merchant", 122, 50),
        # Phase 8 — Hypercare
        ("Hypercare", "Launch-day monitoring (real-time)", "IE on standby monitoring orders and errors.", "ie", 125, 10),
        ("Hypercare", "Day-1 post-launch debrief call", "Quick review of launch-day performance.", "ie", 126, 20),
        ("Hypercare", "Week-1 health check", "Review orders, errors, and churn signals.", "ie", 132, 30),
        ("Hypercare", "Week-2 optimization review", "Surface quick wins based on first-week data.", "ie", 139, 40),
        ("Hypercare", "Week-4 business review", "Formal review of subscription performance.", "ie", 153, 50),
        ("Hypercare", "Formal transition to CSM with handoff document", "Complete handoff with full project documentation.", "ie", 160, 60),
    ]

    for row in standard_tasks:
        c.execute(
            "INSERT INTO project_templates (template_type, group_name, task_title, task_description, owner, days_offset, sort_order) VALUES (?,?,?,?,?,?,?)",
            ("standard",) + row,
        )
    for row in enterprise_tasks:
        c.execute(
            "INSERT INTO project_templates (template_type, group_name, task_title, task_description, owner, days_offset, sort_order) VALUES (?,?,?,?,?,?,?)",
            ("enterprise",) + row,
        )

    conn.commit()
