# SettleDXB — Autonomous Dubai Market-Entry & Ejari Compliance Agent

> **Dubai Chamber Create AI Agents Championship — Best Business AI Agent Track**
>
> An autonomous, stateful B2B agent that compresses Dubai market entry from weeks to minutes: jurisdiction selection, RERA-compliant bilingual lease redlining, and Ejari pre-submission reconciliation — with mandatory human-in-the-loop governance.

---

## The Problem

International SMEs expanding into Dubai routinely hit a regulatory trap that no single vendor solves end-to-end:

1. **Chicken-and-egg licensing.** A Dubai Mainland (DET) license requires an Ejari-registered commercial office. Ejari registration fails if the DET trade name, Title Deed, and lease tenant name don't match — even by a single character.
2. **Arabic-over-English legal asymmetry.** Under UAE law, the **Arabic** lease text prevails in Dubai Rental Disputes Center proceedings. Founders sign bilingual contracts where hidden maintenance liabilities or unilateral eviction terms appear only in Arabic.
3. **Unlawful renewal escalations.** Landlords propose rent hikes that breach **Dubai Decree No. 43 of 2013** (RERA rent slabs) or **Law No. 33 of 2008** (mandatory 90-day notice), and tenants don't have the legal vocabulary to push back.

Existing tools address one slice: lease-reader tools don't touch licensing; company formation agents don't analyze lease clauses; legal counsel is expensive and slow. **No tool unifies all three.**

---

## The Solution

SettleDXB is a **stateful LangGraph agent** with a deterministic regulatory engine and a human-in-the-loop gate. It:

1. **Ingests** the SME's company profile and draft bilingual commercial lease.
2. **Selects** the optimal Dubai jurisdiction (DET Mainland, IFZA, DMCC, DIFC) based on activity, visa quota, and physical-office requirements.
3. **Runs deterministic RERA math** — Decree 43 slab caps and 90-day notice checks — in pure Python (zero hallucination risk).
4. **Diffs the Arabic and English lease clauses** with Gemini, surfacing Arabic-over-English legal discrepancies as CRITICAL findings.
5. **Reconciles Ejari cross-document** consistency (tenant name, Title Deed owner, 10-digit Makani geocode).
6. **Pauses at a Human-in-the-Loop gate** so a compliance officer reviews every finding before any external counter-offer email or license filing is dispatched.
7. **Generates a downloadable bilingual compliance packet PDF** with the redline schedule, counter-offer notice, and audit trail.

Every thread's state is **checkpointed to SQLite**, so the audit trail survives server restarts.

---

## Architecture
