import { useState } from 'react'
import './DocumentGenerate.css'

const TEMPLATES = [
    { id: 'bail', name: 'Bail Application', icon: '🔓', desc: 'Application for regular/anticipatory bail under CrPC' },
    { id: 'legal_notice', name: 'Legal Notice', icon: '📩', desc: 'Formal legal notice under various statutory provisions' },
    { id: 'affidavit', name: 'Affidavit', icon: '📜', desc: 'Sworn statement for court or official proceedings' },
    { id: 'poa', name: 'Power of Attorney', icon: '🤝', desc: 'General or specific power of attorney document' },
    { id: 'complaint', name: 'Complaint/Petition', icon: '📝', desc: 'Criminal complaint or civil petition draft' },
    { id: 'appeal', name: 'Appeal Memorandum', icon: '⚖️', desc: 'Appeal against lower court order or judgment' },
]

const COURTS = [
    'Sessions Court', 'District Court', 'High Court', 'Supreme Court',
    'Metropolitan Magistrate', 'Chief Judicial Magistrate',
]

function DocumentGenerate({ onBack }) {
    const [selectedTemplate, setSelectedTemplate] = useState(null)
    const [formData, setFormData] = useState({})
    const [isGenerating, setIsGenerating] = useState(false)
    const [generatedDraft, setGeneratedDraft] = useState(null)
    const [error, setError] = useState(null)

    const handleInputChange = (e) => {
        const { name, value } = e.target
        setFormData(prev => ({ ...prev, [name]: value }))
    }

    const handleGenerate = async (e) => {
        if (e) e.preventDefault()
        setIsGenerating(true)
        setError(null)

        try {
            const response = await fetch('/api/documents/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    template_type: selectedTemplate.id || selectedTemplate,
                    form_data: formData
                })
            })

            if (!response.ok) {
                const data = await response.json()
                throw new Error(data.detail || 'Generation failed')
            }

            const result = await response.json()
            setGeneratedDraft(result.document_draft)

            if (result.status === 'demo') {
                setError('Using offline template engine (AI service temporarily unavailable)')
            }
        } catch (err) {
            console.error('Generation Error:', err)
            setError('Connection error. Falling back to local template.')
            // Fallback to local demo
            if (selectedTemplate.id === 'bail' || selectedTemplate === 'bail') {
                setGeneratedDraft(generateBailDemoDraft(formData))
            } else {
                setGeneratedDraft(generateTemplateDraft(selectedTemplate.id || selectedTemplate, formData))
            }
        } finally {
            setIsGenerating(false)
        }
    }

    const generateBailDemoDraft = (data) => {
        return `IN THE COURT OF ${(data.court || 'SESSIONS COURT').toUpperCase()}
AT [JURISDICTION]

BAIL APPLICATION NO. ________ OF 2026

IN THE MATTER OF:

${data.petitionerName || '[PETITIONER NAME]'}
S/o [Father's Name]
R/o ${data.petitionerAddress || '[Address]'}
                                                    ... APPLICANT/ACCUSED

VERSUS

State of [State]
Through: ${data.prosecutorName || 'Public Prosecutor'}
                                                    ... RESPONDENT

CASE NO.: ${data.caseNumber || '[FIR/Case Number]'}

SECTIONS: ${data.offenseSections || '[Sections]'}

APPLICATION FOR GRANT OF REGULAR BAIL UNDER SECTION 439 CR.P.C.

MOST RESPECTFULLY SHOWETH:

1. That the applicant is in judicial custody since _______ in connection with the aforesaid case registered at Police Station _______.

2. BRIEF FACTS OF THE CASE:
${data.caseFacts || '[Case facts to be inserted]'}

3. GROUNDS FOR BAIL:
${data.groundsForBail ? data.groundsForBail.split('\n').map((g, i) => `   ${i + 1}. ${g}`).join('\n') : '   [Grounds to be inserted]'}

4. That the applicant has been in custody for ${data.priorCustodyDays || '___'} days and the investigation is complete/charge sheet has been filed.

5. That the applicant is not a flight risk and has deep roots in the community.

6. That the applicant undertakes to not tamper with evidence or influence witnesses.

PRAYER:

In view of the above submissions, it is most respectfully prayed that this Hon'ble Court may be pleased to grant regular bail to the applicant on such terms and conditions as this Hon'ble Court may deem fit and proper.

AND FOR THIS ACT OF KINDNESS, THE APPLICANT SHALL EVER BE GRATEFUL.

Place: ___________
Date: ___________
                                                    APPLICANT
                                              Through Counsel

VERIFICATION:

I, ${data.petitionerName || '[Petitioner Name]'}, do hereby verify that the contents of the above application are true and correct to my knowledge and belief.

Verified at _______ on this _______ day of _______ 2026.

                                                    DEPONENT`
    }

    const generateTemplateDraft = (templateId, data) => {
        const templates = {
            legal_notice: `LEGAL NOTICE

Date: ${new Date().toLocaleDateString('en-IN')}

TO,
${data.recipientName || '[Recipient Name]'}
${data.recipientAddress || '[Recipient Address]'}

FROM,
${data.senderName || '[Sender Name]'}
Through Advocate: ${data.advocateName || '[Advocate Name]'}

SUBJECT: ${data.subject || 'LEGAL NOTICE UNDER SECTION _______ OF _______'}

Sir/Madam,

Under the instructions and on behalf of my client, ${data.senderName || '[Client Name]'}, I do hereby serve upon you the following Legal Notice:

${data.noticeContent || `1. That my client is [describe relationship/transaction].

2. That you have [describe the grievance/issue].

3. That despite repeated requests, you have failed to [describe the demanded action].`}

You are hereby called upon to ${data.demand || '[state the demand/action required]'} within 15 days from the receipt of this notice, failing which my client shall be constrained to initiate appropriate legal proceedings against you at your risk, cost and consequences.

Please treat this as the final notice before legal proceedings.

${data.advocateName || '[Advocate Name]'}
Advocate
[Bar Registration No.]
[Address]`,

            affidavit: `AFFIDAVIT

I, ${data.deponentName || '[Deponent Name]'}, aged ${data.age || '____'} years,
S/o / D/o / W/o ${data.parentName || '[Father/Spouse Name]'},
R/o ${data.address || '[Complete Address]'},

do hereby solemnly affirm and declare as under:

1. That I am the deponent herein and am competent to swear this affidavit.

2. That ${data.purpose || '[State the purpose of the affidavit]'}.

${data.statements || `3. That [Statement 1].

4. That [Statement 2].

5. That [Statement 3].`}

6. That the contents of this affidavit are true and correct to the best of my knowledge and belief. Nothing material has been concealed therefrom.

VERIFICATION:

Verified at ${data.place || '[Place]'} on this _____ day of _______ 2026 that the contents of the above affidavit are true and correct to the best of my knowledge and belief.

DEPONENT

(${data.deponentName || '[Deponent Name]'})`,

            poa: `POWER OF ATTORNEY

KNOW ALL MEN BY THESE PRESENTS:

I, ${data.principalName || '[Principal Name]'}, aged ${data.principalAge || '____'} years,
S/o / D/o / W/o ${data.principalParent || '[Parent/Spouse Name]'},
R/o ${data.principalAddress || '[Address]'},

DO HEREBY appoint, nominate, constitute and authorize:

${data.attorneyName || '[Attorney Name]'}, aged ${data.attorneyAge || '____'} years,
R/o ${data.attorneyAddress || '[Attorney Address]'},

as my true and lawful attorney to act, do and execute all or any of the following acts, deeds and things on my behalf:

${data.powers || `1. To manage and administer my property situated at _______.
2. To execute, sign and deliver all documents and papers.
3. To appear before any authority, court or tribunal.
4. To receive and collect rents, payments and dues.
5. To do all acts, deeds and things as may be necessary.`}

AND I do hereby agree and undertake to ratify and confirm all such acts, deeds and things lawfully done by my said attorney by virtue of this Power of Attorney.

IN WITNESS WHEREOF, I have set my hand on this _____ day of _______ 2026.

EXECUTANT
(${data.principalName || '[Principal Name]'})

WITNESSES:
1. _______________
2. _______________`,

            complaint: `IN THE COURT OF ${(data.court || 'CHIEF JUDICIAL MAGISTRATE').toUpperCase()}
AT ${(data.jurisdiction || '[JURISDICTION]').toUpperCase()}

COMPLAINT CASE NO. _______ OF 2026

${data.complainantName || '[Complainant Name]'}
${data.complainantAddress || '[Address]'}
                                                    ... COMPLAINANT

VERSUS

${data.accusedName || '[Accused Name]'}
${data.accusedAddress || '[Address]'}
                                                    ... ACCUSED

COMPLAINT UNDER SECTIONS ${data.sections || '[Sections]'}

RESPECTFULLY SHOWETH:

1. That the complainant is a respectable citizen and is filing this complaint for the offences committed by the accused.

${data.facts || `2. That [describe the facts of the case].

3. That [describe the specific incidents].

4. That [describe the harm/injury suffered].`}

5. That the complainant has a reasonable cause to believe that the accused has committed the aforesaid offences.

PRAYER:

It is, therefore, most respectfully prayed that this Hon'ble Court may be pleased to:
a) Take cognizance of the offences;
b) Summon the accused and try him/her as per law;
c) Pass such other order(s) as deemed fit.

AND FOR THIS ACT OF KINDNESS, THE COMPLAINANT SHALL EVER BE GRATEFUL.

Place: ___________
Date: ___________

COMPLAINANT
Through Counsel`,

            appeal: `IN THE HON'BLE ${(data.court || 'HIGH COURT').toUpperCase()} OF ${(data.state || '[STATE]').toUpperCase()}

CRIMINAL/CIVIL APPEAL NO. _______ OF 2026

${data.appellantName || '[Appellant Name]'}
                                                    ... APPELLANT

VERSUS

${data.respondentName || '[Respondent Name]'}
                                                    ... RESPONDENT

APPEAL AGAINST THE ORDER/JUDGMENT DATED ${data.impugnedDate || '_______'}
PASSED BY THE COURT OF ${data.lowerCourt || '[Lower Court]'}
IN CASE NO. ${data.lowerCaseNo || '_______'}

MEMORANDUM OF APPEAL

The appellant above-named most respectfully begs to prefer this appeal against the Order/Judgment dated ${data.impugnedDate || '_______'} on the following grounds:

GROUNDS OF APPEAL:

${data.grounds || `1. That the learned lower court erred in law and in fact in passing the impugned order.

2. That the impugned order is against the weight of evidence on record.

3. That the learned court failed to appreciate the evidence in its correct perspective.

4. That the punishment/order is excessive and disproportionate.`}

PRAYER:

It is, therefore, most respectfully prayed that this Hon'ble Court may be pleased to:
a) Accept this Appeal;
b) Set aside / modify the impugned Order/Judgment;
c) Pass such other order(s) as deemed fit in the interest of justice.

AND FOR THIS ACT OF KINDNESS, THE APPELLANT SHALL EVER BE GRATEFUL.

Place: ___________
Date: ___________

APPELLANT
Through Counsel`
        }

        return templates[templateId] || 'Template not available.'
    }

    const copyToClipboard = () => {
        navigator.clipboard.writeText(generatedDraft)
    }

    const downloadDraft = () => {
        const template = TEMPLATES.find(t => t.id === selectedTemplate)
        const blob = new Blob([generatedDraft], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${template?.name || 'document'}_${formData.caseNumber || 'draft'}.txt`
        a.click()
        URL.revokeObjectURL(url)
    }

    const renderFormFields = () => {
        switch (selectedTemplate) {
            case 'bail':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>📋 Basic Information</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Petitioner Name *</label>
                                    <input type="text" name="petitionerName" value={formData.petitionerName || ''} onChange={handleInputChange} placeholder="Full legal name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Case Number *</label>
                                    <input type="text" name="caseNumber" value={formData.caseNumber || ''} onChange={handleInputChange} placeholder="e.g., FIR No. 123/2024" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Court</label>
                                    <select name="court" value={formData.court || 'Sessions Court'} onChange={handleInputChange}>
                                        {COURTS.map(c => <option key={c} value={c}>{c}</option>)}
                                    </select>
                                </div>
                                <div className="gen-form-group">
                                    <label>Days in Custody</label>
                                    <input type="number" name="priorCustodyDays" value={formData.priorCustodyDays || ''} onChange={handleInputChange} placeholder="e.g., 45" min="0" />
                                </div>
                            </div>
                        </div>
                        <div className="gen-form-section">
                            <h4>⚖️ Case Details</h4>
                            <div className="gen-form-group full">
                                <label>Charged Sections *</label>
                                <input type="text" name="offenseSections" value={formData.offenseSections || ''} onChange={handleInputChange} placeholder="e.g., IPC 302, IPC 307" required />
                            </div>
                            <div className="gen-form-group full">
                                <label>Brief Facts *</label>
                                <textarea name="caseFacts" value={formData.caseFacts || ''} onChange={handleInputChange} placeholder="Describe the alleged incident..." rows={4} required />
                            </div>
                            <div className="gen-form-group full">
                                <label>Grounds for Bail (one per line)</label>
                                <textarea name="groundsForBail" value={formData.groundsForBail || ''} onChange={handleInputChange} placeholder="No flight risk&#10;No criminal record&#10;Investigation complete" rows={3} />
                            </div>
                        </div>
                    </>
                )

            case 'legal_notice':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>📩 Notice Details</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Sender Name *</label>
                                    <input type="text" name="senderName" value={formData.senderName || ''} onChange={handleInputChange} placeholder="Client name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Recipient Name *</label>
                                    <input type="text" name="recipientName" value={formData.recipientName || ''} onChange={handleInputChange} placeholder="Recipient name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Advocate Name</label>
                                    <input type="text" name="advocateName" value={formData.advocateName || ''} onChange={handleInputChange} placeholder="Advocate name" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Subject *</label>
                                    <input type="text" name="subject" value={formData.subject || ''} onChange={handleInputChange} placeholder="Notice subject" required />
                                </div>
                            </div>
                            <div className="gen-form-group full">
                                <label>Notice Content</label>
                                <textarea name="noticeContent" value={formData.noticeContent || ''} onChange={handleInputChange} placeholder="Describe the grievance and demands..." rows={5} />
                            </div>
                            <div className="gen-form-group full">
                                <label>Demand / Action Required</label>
                                <textarea name="demand" value={formData.demand || ''} onChange={handleInputChange} placeholder="State what action you require..." rows={2} />
                            </div>
                        </div>
                    </>
                )

            case 'affidavit':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>📜 Deponent Details</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Deponent Name *</label>
                                    <input type="text" name="deponentName" value={formData.deponentName || ''} onChange={handleInputChange} placeholder="Full name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Age *</label>
                                    <input type="number" name="age" value={formData.age || ''} onChange={handleInputChange} placeholder="Age" min="18" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Parent/Spouse Name</label>
                                    <input type="text" name="parentName" value={formData.parentName || ''} onChange={handleInputChange} placeholder="Father/Spouse name" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Place</label>
                                    <input type="text" name="place" value={formData.place || ''} onChange={handleInputChange} placeholder="City" />
                                </div>
                            </div>
                            <div className="gen-form-group full">
                                <label>Address</label>
                                <input type="text" name="address" value={formData.address || ''} onChange={handleInputChange} placeholder="Complete address" />
                            </div>
                            <div className="gen-form-group full">
                                <label>Purpose of Affidavit</label>
                                <textarea name="purpose" value={formData.purpose || ''} onChange={handleInputChange} placeholder="State the purpose..." rows={3} />
                            </div>
                            <div className="gen-form-group full">
                                <label>Statements (numbered)</label>
                                <textarea name="statements" value={formData.statements || ''} onChange={handleInputChange} placeholder="3. That ...&#10;4. That ...&#10;5. That ..." rows={4} />
                            </div>
                        </div>
                    </>
                )

            case 'poa':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>🤝 Principal & Attorney</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Principal Name *</label>
                                    <input type="text" name="principalName" value={formData.principalName || ''} onChange={handleInputChange} placeholder="Principal name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Attorney Name *</label>
                                    <input type="text" name="attorneyName" value={formData.attorneyName || ''} onChange={handleInputChange} placeholder="Attorney name" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Principal Address</label>
                                    <input type="text" name="principalAddress" value={formData.principalAddress || ''} onChange={handleInputChange} placeholder="Address" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Attorney Address</label>
                                    <input type="text" name="attorneyAddress" value={formData.attorneyAddress || ''} onChange={handleInputChange} placeholder="Address" />
                                </div>
                            </div>
                            <div className="gen-form-group full">
                                <label>Powers to be Granted</label>
                                <textarea name="powers" value={formData.powers || ''} onChange={handleInputChange} placeholder="1. To manage property...&#10;2. To sign documents..." rows={5} />
                            </div>
                        </div>
                    </>
                )

            case 'complaint':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>📝 Complaint Details</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Complainant Name *</label>
                                    <input type="text" name="complainantName" value={formData.complainantName || ''} onChange={handleInputChange} placeholder="Complainant" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Accused Name *</label>
                                    <input type="text" name="accusedName" value={formData.accusedName || ''} onChange={handleInputChange} placeholder="Accused" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Court</label>
                                    <input type="text" name="court" value={formData.court || ''} onChange={handleInputChange} placeholder="Court name" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Sections</label>
                                    <input type="text" name="sections" value={formData.sections || ''} onChange={handleInputChange} placeholder="e.g., 420, 406 IPC" />
                                </div>
                            </div>
                            <div className="gen-form-group full">
                                <label>Facts of the Case</label>
                                <textarea name="facts" value={formData.facts || ''} onChange={handleInputChange} placeholder="Describe the incidents..." rows={5} />
                            </div>
                        </div>
                    </>
                )

            case 'appeal':
                return (
                    <>
                        <div className="gen-form-section">
                            <h4>⚖️ Appeal Details</h4>
                            <div className="gen-form-grid">
                                <div className="gen-form-group">
                                    <label>Appellant Name *</label>
                                    <input type="text" name="appellantName" value={formData.appellantName || ''} onChange={handleInputChange} placeholder="Appellant" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Respondent Name *</label>
                                    <input type="text" name="respondentName" value={formData.respondentName || ''} onChange={handleInputChange} placeholder="Respondent" required />
                                </div>
                                <div className="gen-form-group">
                                    <label>Appellate Court</label>
                                    <input type="text" name="court" value={formData.court || ''} onChange={handleInputChange} placeholder="e.g., High Court" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Impugned Order Date</label>
                                    <input type="date" name="impugnedDate" value={formData.impugnedDate || ''} onChange={handleInputChange} />
                                </div>
                                <div className="gen-form-group">
                                    <label>Lower Court</label>
                                    <input type="text" name="lowerCourt" value={formData.lowerCourt || ''} onChange={handleInputChange} placeholder="Court that passed order" />
                                </div>
                                <div className="gen-form-group">
                                    <label>Lower Court Case No.</label>
                                    <input type="text" name="lowerCaseNo" value={formData.lowerCaseNo || ''} onChange={handleInputChange} placeholder="Case number" />
                                </div>
                            </div>
                            <div className="gen-form-group full">
                                <label>Grounds of Appeal</label>
                                <textarea name="grounds" value={formData.grounds || ''} onChange={handleInputChange} placeholder="1. That the learned court erred...&#10;2. That the order is against evidence..." rows={5} />
                            </div>
                        </div>
                    </>
                )

            default:
                return null
        }
    }

    // Template selection view
    if (!selectedTemplate) {
        return (
            <div className="doc-generate animate-fade-in">
                <div className="doc-subview-header">
                    <button className="back-btn" onClick={onBack}>← Back to Hub</button>
                    <div className="subview-title-group">
                        <h2 className="subview-title">Generate New Document</h2>
                        <p className="subview-subtitle">Select a template to get started</p>
                    </div>
                </div>

                <div className="template-grid">
                    {TEMPLATES.map(template => (
                        <div
                            key={template.id}
                            className="template-card glass-card"
                            onClick={() => { setSelectedTemplate(template.id); setFormData({}); setGeneratedDraft(null) }}
                        >
                            <span className="template-icon">{template.icon}</span>
                            <h3 className="template-name">{template.name}</h3>
                            <p className="template-desc">{template.desc}</p>
                            <span className="template-select-badge">Select →</span>
                        </div>
                    ))}
                </div>
            </div>
        )
    }

    // Draft result view
    if (generatedDraft) {
        const template = TEMPLATES.find(t => t.id === selectedTemplate)
        return (
            <div className="doc-generate animate-fade-in">
                <div className="doc-subview-header">
                    <button className="back-btn" onClick={onBack}>← Back to Hub</button>
                    <div className="subview-title-group">
                        <h2 className="subview-title">{template?.icon} {template?.name}</h2>
                        <p className="subview-subtitle">Generated document ready for review</p>
                    </div>
                </div>

                <div className="gen-result glass-card">
                    <div className="gen-result-actions">
                        <button onClick={() => { setGeneratedDraft(null) }} className="gen-action-btn secondary">← Edit Details</button>
                        <div className="gen-action-group">
                            <button onClick={copyToClipboard} className="gen-action-btn">📋 Copy</button>
                            <button onClick={downloadDraft} className="gen-action-btn primary">⬇️ Download</button>
                        </div>
                    </div>
                    <pre className="gen-draft-content">{generatedDraft}</pre>
                </div>

                <p className="gen-disclaimer">
                    ⚠️ This is an AI-generated draft. Please review and modify as per your specific requirements. Consult a qualified advocate before filing.
                </p>
            </div>
        )
    }

    // Form view
    const template = TEMPLATES.find(t => t.id === selectedTemplate)
    return (
        <div className="doc-generate animate-fade-in">
            <div className="doc-subview-header">
                <button className="back-btn" onClick={onBack}>← Back to Hub</button>
                <div className="subview-title-group">
                    <h2 className="subview-title">{template?.icon} {template?.name}</h2>
                    <p className="subview-subtitle">Fill in the details below</p>
                </div>
                <button className="change-template-btn" onClick={() => { setSelectedTemplate(null); setFormData({}) }}>
                    Change Template
                </button>
            </div>

            <form onSubmit={handleGenerate} className="gen-form glass-card">
                {renderFormFields()}

                {error && (
                    <div className="gen-error">
                        <span>⚠️</span> {error}
                    </div>
                )}

                <button type="submit" className="gen-submit-btn" disabled={isGenerating}>
                    {isGenerating ? (
                        <><span className="spinner"></span> Generating...</>
                    ) : (
                        <><span>✨</span> Generate {template?.name}</>
                    )}
                </button>
            </form>

            <p className="gen-disclaimer">
                ⚠️ AI-generated document. Review and consult a qualified advocate before filing.
            </p>
        </div>
    )
}

export default DocumentGenerate
