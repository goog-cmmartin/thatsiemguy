# **Web Application Planning & Workflow Design Guide**

### **Step 1: Core Concept & Vision Statement**

* **Vision Statement**

To provide Google SecOps Detection Engineers with a dedicated web application for managing the entire lifecycle of SIGMA detection rules. The platform will streamline the import from standard and custom rule libraries, automate the conversion and deployment of rules into Google SecOps, and provide critical performance analytics to optimize the organization's detection posture, filling a key gap in the current security tooling landscape.

* **Problem:** What specific problem are you solving?

Managing the workflow and lifecycle of SIGMA rules in Google SecOps by creating an import and management application.  Rule performance and efficiency monitoring analysis is also provided so to know what rules are working well, or not. 

* **Solution:** How does your application solve this problem?

Default rule content will use the SigmaHQ (https://github.com/SigmaHQ/sigma/tree/master) repository but the application should support the concept of adding a "Library" so a user could add their own custom rule repositories.

For converting the Sigma rules into YARA-L the Sigma Rule Converter (AttackIQ pySigma-backend-secops) AttackIQ pySigma-backend-secops library will be used (https://github.com/AttackIQ/pySigma-backend-secops)

For the authentication and access to interact with Google SecOps the secops-wrapper SDK will be used \- [https://github.com/google/secops-wrapper](https://github.com/google/secops-wrapper)

For storing state around the application, such as deployed rules, sigma libraries, secops tenants, rule performance, etc.. a sqllite db will be used

For the web frontend, javascript, and css library this is open and no specific library is preferred

* **Target Audience:** Who are your primary users? (e.g., students, small business owners, artists)

Google SecOps Detection Engineers

* **Unique Value Proposition:** What makes your application different from or better than existing solutions?

There is no equivalent application that achieve this functionality at this time

### **Step 2: Feature Brainstorming & Prioritization**

* **Minimum Viable Product (MVP)**.

| Feature | Priority | Description |
| :---- | :---- | :---- |
| Web based interface | Must-Have | A basic web interface to trigger rule conversion and deployment. |
| Add/Configure a Sigma Library | Must-Have | Ability to set up the initial source Sigma rule library (e.g., SigmaHQ). |
| Add/Configure a SecOps Tenant | Must-Have | Ability to set up the initial destination SecOps tenant. |
| Convert Sigma rules to YARA-L | Must-Have | Use the AttackIQ library to bulk convert rules. Track success/failure. |
| Deploy YARA-L rules to SecOps | Must-Have | Deploy successfully converted rules to a configured SecOps tenant. |
| Manage Multiple Tenants/Libraries | Should-Have | Enhance the UI to support adding, editing, and removing multiple tenants and libraries. |
| Monitor performance of rules | Could-Have | Check the status and performance of deployed rules. |
| Onboarding Wizard | Could-Have | A GUI wizard to guide the initial setup. |
| Meta tagging analysis | Could-Have | Analyse and report on the meta tag values on deployed rules |
| Audit logging | Should-Have | A detailed audit log of all activities performed in the application |
| Test YARA-L rules before deploying to SecOps | Could-Have | Before deploying a YARA-L rule run a test to evaluate if or how many matches it generates |

The **MoSCoW method**:

* **Must-Have:** Core features without which the app is not functional (e.g., user registration, product upload).  
* **Should-Have:** Important features that are not critical for the initial launch (e.g., user reviews, artist profiles).  
* **Could-Have:** Desirable but non-essential features (e.g., social media integration, a blog).  
* **Won't-Have (for now):** Features that are out of scope for the initial release.

### **Step 3: User Personas & User Stories**

"As a **Detection Engineer setting up the tool for the first time**, I want to **add my SecOps tenant credentials and specify the Sigma rule library I want to use**, so that **I can prepare the application for converting and deploying rules**."

"As a **Detection Engineer**, I want to **import, convert, and deploy specific Sigma rules** so that I can **quickly expand our threat coverage beyond what is provided by default in Google SecOps**."

"As a **Detection Engineer**, I want to **view performance metrics for my deployed rules** so that I can **identify and disable noisy or ineffective detections to improve our SecOps efficiency**."

**Example User Persona: “Calico Jack”**

* **Bio:** Detection Engineer  
* **Goals:** Wants to easily setup a Sigma to YARA-L, and rules performance monitoring application

**Example User Persona: “Captain Crabby”**

* **Bio:** Detection Engineer  
* **Goals:** Wants to easily be able to implement Sigma detection content for specific applications, technologies or threats,  as either part of an initial SecOps deployment, or an ongoing deployment, that are not available or covered from Google SecOps Curated Detections

**Example User Persona: "Billy Bones"**

* **Bio:** Detection Engineer  
* **Goals:** Wants to easily to verify the performance of existing SecOps Rules, and find noisy or stale detection content within their deployed Google SecOps 

### **Step 4: Workflow Mapping (Flowcharts)**

This is where you visually map out user journeys. Use a simple flowchart tool or even pen and paper. This is critical for defining both front-end navigation and back-end logic.

**Key Workflows to Map:**

#### Workflow 1: First-Time Setup (Onboarding)

* User Action: Navigates to the application for the first time.  
* System Response: Presents a setup screen/wizard.  
* User Action: Enters details for a new SecOps Tenant (Name, GUID, Region, Project ID).  
* User Action: Clicks a "Test Connection" button to validate credentials.  
* System Response: Shows "Success" or "Error" message.  
* User Action: Saves the tenant configuration.  
* System Response: Redirects the user to the main application dashboard.

---

#### Workflow 2: Rule Conversion & Deployment (Captain Crabby's Journey)

1. Navigate & Select: The user goes to the "Sigma Library" page. They see a filterable, searchable list of all available Sigma rules.  
2. Choose Rules: The user selects the specific rules they want to implement using checkboxes next to each rule name.  
3. Initiate Conversion: The user clicks a "Convert Selected Rules" button.  
4. Review Results: The system processes the rules and displays a "Conversion Report" showing which rules converted successfully and which failed (with a reason, if possible).  
5. Select for Deployment: From the list of successfully converted rules in the report, the user selects the ones they want to deploy.  
6. Choose Tenant & Deploy: The user chooses a target SecOps tenant from a dropdown menu and clicks "Deploy."  
7. Confirmation: The system shows a confirmation message indicating the rules have been successfully deployed.

---

#### Workflow 3: Performance Monitoring (Billy Bones' Journey)

1. Navigate: The user goes to the "Rule Performance" or "Dashboard" page.  
2. Filter by Tenant: The user selects a SecOps tenant from a dropdown to view its deployed rules.  
3. Analyze Data: The system displays a table of all rules for that tenant. The table includes columns like "Rule Name," "Status (Live/Disabled)," "Detection Count," and "Runtime Errors."  
4. Identify Issues: The user can sort the table (e.g., by detection count) to easily find noisy or underperforming rules.

### **Step 5: Data Modeling & Database Schema**

**Entities:** These are the main "tables" in your database.

* `Tenants`: Stores Google SecOps tenant connection details.  
* `SigmaLibraries`: Stores information about the source Sigma rule repositories.  
* `SigmaRules`: Stores individual Sigma rules fetched from a library.  
* `YaraLRules`: Stores the successfully converted YARA-L content.  
* `Deployments`: A record of which YARA-L rule has been deployed to which tenant.

**Attributes (Columns for each table):**

* **Tenants Table:**  
  * `tenant_id` (Primary Key)  
  * `name` (Text, e.g., "Production Environment")  
  * `guid` (Text)  
  * `region` (Text)  
  * `gcp_project_id` (Text)  
  * `is_default` (Boolean)  
* **SigmaLibraries Table:**  
  * `library_id` (Primary Key)  
  * `name` (Text, e.g., "SigmaHQ Public")  
  * `source_path` (Text, URL or local file path)  
  * `last_synced_at` (Timestamp)  
* **SigmaRules Table:**  
  * `rule_id` (Primary Key)  
  * `library_id` (Foreign Key to `SigmaLibraries`)  
  * `title` (Text)  
  * `file_path` (Text, relative path in the library)  
  * `raw_content` (Text, the original Sigma YAML)  
  * `conversion_status` (Text: "pending", "success", "failed")  
  * `conversion_error` (Text, stores error message if conversion failed)  
* **YaraLRules Table:**  
  * `yaral_rule_id` (Primary Key)  
  * `sigma_rule_id` (Foreign Key to `SigmaRules`, one-to-one relationship)  
  * `converted_content` (Text, the generated YARA-L rule)  
  * `created_at` (Timestamp)  
* **Deployments Table:**  
  * `deployment_id` (Primary Key)  
  * `yaral_rule_id` (Foreign Key to `YaraLRules`)  
  * `tenant_id` (Foreign Key to `Tenants`)  
  * `deployed_at` (Timestamp)  
  * `status` (Text: "live", "disabled", "error")  
  * `detection_count` (Integer, for performance monitoring)  
  * `last_perf_check` (Timestamp)

**Relationships:**

* A `SigmaLibrary` can have **many** `SigmaRules`.  
* A `SigmaRule` can have **one** `YaraLRule` (after a successful conversion).  
* A `YaraLRule` can have **many** `Deployments` (deployed to different tenants).  
* A `Tenant` can have **many** `Deployments`.

### **Step 6: Define Your API Endpoints**

### **Step 6: Define Your API Endpoints**

Your frontend application will communicate with your backend database through an API. Here is a proposed set of RESTful API endpoints based on the defined workflows and data model.

#### **Tenant Management**

* `GET /api/tenants` \- Get a list of all configured SecOps tenants.  
* `POST /api/tenants` \- Create a new SecOps tenant.  
* `GET /api/tenants/{id}` \- Get details for a single tenant.  
* `PUT /api/tenants/{id}` \- Update a tenant's details.  
* `DELETE /api/tenants/{id}` \- Remove a tenant.  
* `POST /api/tenants/{id}/test` \- Test the connection to a SecOps tenant to verify credentials.

#### **Sigma Library Management**

* `GET /api/libraries` \- Get a list of all configured Sigma libraries.  
* `POST /api/libraries` \- Add a new Sigma library.  
* `DELETE /api/libraries/{id}` \- Remove a Sigma library.  
* `POST /api/libraries/{id}/sync` \- Trigger a background job to sync the latest rules from the library's source.

#### **Rule Management & Conversion**

* `GET /api/sigma-rules` \- Get a list of all Sigma rules. Supports filtering by library, title, and conversion status (e.g., `/api/sigma-rules?library_id=1&status=pending`).  
* `GET /api/sigma-rules/{id}` \- Get the raw content and details of a single Sigma rule.  
* `POST /api/sigma-rules/convert` \- Trigger the conversion process. The request body will contain a list of `sigma_rule_id`s to be converted. Returns a job ID to track the status.  
* `GET /api/conversion-jobs/{job_id}` \- Get the status and results of a conversion job (e.g., success/fail list).

#### **Deployment & Performance**

* `GET /api/deployments` \- Get a list of all deployed rules. Supports filtering by tenant (e.g., `/api/deployments?tenant_id=1`).  
* `POST /api/deployments` \- Deploy a converted rule. The request body will contain the `yaral_rule_id` and the target `tenant_id`.  
* `DELETE /api/deployments/{id}` \- Undeploy a rule from a tenant.  
* `POST /api/deployments/sync-performance` \- Trigger a background job to fetch the latest performance stats (detection count, status) for all rules in a specific tenant. Request body contains `tenant_id`.
