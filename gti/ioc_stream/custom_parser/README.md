# GTI_IOC_STREAM

The following field mapping summary from the original raw log into UDM was created automatically using Gemini.

## Domain object mapping 

[Domain Object](https://gtidocs.virustotal.com/reference/domains-object)

__metadata:__
- __productLogId__: `context_attributes.notification_id` 
- __eventTimestamp__: `context_attributes.notification_date`
- __eventType__: "GENERIC_EVENT" (Hardcoded)
- __vendorName__: "Google Cloud" (Hardcoded)
- __productName__: "IOC Stream" (Hardcoded)
- __productEventType__: `type`
- __urlBackToProduct__: Constructed using the type `"https://www.virustotal.com/gui/{type}/` + `id` 
- __logType__: "ACME_GTI_IOC_STREAM" (Hardcoded)

__additional:__
- __suspicious__: `last_analysis_stats.suspicious` 
- __undetected__: `last_analysis_stats.undetected` 
- __harmless__: `last_analysis_stats.harmless` 
- __timeout__: `last_analysis_stats.timeout` 
- __malicious__: `last_analysis_stats.malicious` 

__target:__
- __domain__:
  - __name__: `id` 
  - __jarm__: `attributes.jarm` 
  - __lastDnsRecords__: `attributes.last_dns_records` 
    - __type__: `type` in `attributes.last_dns_records`
    - __value__: `value` in `attributes.last_dns_records`
  - __lastHttpsCertificate__:
    - __serialNumber__: `attributes.last_https_certificate.serial_number` 
    - __subject__:
      - __commonName__: `attributes.last_https_certificate.subject.CN` 

__securityResult:__
- __ruleName__: `context_attributes.hunting_info.rule_name` 
- __summary__: `attributes.threat_severity.level_description` 
- __severityDetails__: `attributes.threat_severity.threat_severity_level` 
- __urlBackToProduct__: Constructed using the rule ID: `"https://yara-editor.virustotal.com/livehunt/` + `context_attributes.sources[0].id` 
- __ruleId__: `context_attributes.sources[0].id` 
- __ruleLabels__:
  - __key__: "sources_label" (Hardcoded)
  - __value__: `context_attributes.sources[0].label` 
  - __key__: "sources_type" (Hardcoded)
  - __value__: `context_attributes.sources[0].type`
- __lastUpdatedTime__: `attributes.threat_severity.last_analysis_date`
- __confidenceScore__: `attributes.mandiant_ic_score` 


## File object mapping

[File Object](https://gtidocs.virustotal.com/reference/file-object)

__metadata:__

- __productLogId__: `context_attributes.notification_id`
- __eventTimestamp__: `context_attributes.notification_date` 
- __eventType__: "GENERIC_EVENT" (Hardcoded)
- __vendorName__: "Google Cloud" (Hardcoded)
- __productName__: "IOC Stream" (Hardcoded)
- __productEventType__: `type` (file)
- __urlBackToProduct__: Constructed using the type and id: `https://www.virustotal.com/gui/{type}/{id}`
- __logType__: "ACME_GTI_IOC_STREAM" (Hardcoded)

__additional:__
- __malicious__: `last_analysis_stats.malicious`
- __suspicious__: `last_analysis_stats.suspicious`
- __undetected__: `last_analysis_stats.undetected`
- __harmless__: `last_analysis_stats.harmless`
- __timeout__: `last_analysis_stats.timeout`

__securityResult:__
- __ruleName__: `context_attributes.hunting_info.rule_name`
- __summary__: `attributes.threat_severity.level_description`
- __severityDetails__: `attributes.threat_severity.threat_severity_level`
- __urlBackToProduct__: Constructed using the rule ID: `https://yara-editor.virustotal.com/livehunt/{context_attributes.sources.0.id}`
- __ruleId__: `context_attributes.sources[0].id`
- __ruleLabels__:
  - __key__: "sources_label" (Hardcoded)
  - __value__: `context_attributes.sources[0].label`
  - __key__: "sources_type" (Hardcoded)
  - __value__: `context_attributes.sources[0].type`

__about:__
- __file__:
  - __sha256__: `attributes.sha256`
  - __md5__: `attributes.md5` 
  - __sha1__: `attributes.sha1` 
  - __size__: `attributes.size` 
  - __ssdeep__: `attributes.ssdeep` 
  - __vhash__: `attributes.vhash`
  - __lastModificationTime__: `attributes.last_modification_date`
  - __lastAnalysisTime__: `attributes.last_analysis_date`
  - __tags__: `attributes.type_tags`
  - __firstSubmissionTime__: `attributes.first_submission_date`
  - __lastSubmissionTime__: `attributes.last_submission_date`

## IP Address Object Mapping

[IP Address Object](https://gtidocs.virustotal.com/reference/ip-object)

__metadata:__
- __productLogId__: `context_attributes.notification_id` 
- __eventTimestamp__: `context_attributes.notification_date`
- __eventType__: "GENERIC_EVENT" (Hardcoded)
- __vendorName__: "Google Cloud" (Hardcoded)
- __productName__: "IOC Stream" (Hardcoded)
- __productEventType__: `type` (ip_address)
- __urlBackToProduct__: Constructed using the type and id: `https://www.virustotal.com/gui/{type}/{id}`
- __logType__: "GTI_IOC_STREAM" (Hardcoded)

__additional:__
- __malicious__: `last_analysis_stats.malicious`
- __suspicious__: `last_analysis_stats.suspicious`
- __undetected__: `last_analysis_stats.undetected`
- __harmless__: `last_analysis_stats.harmless`
- __timeout__: `last_analysis_stats.timeout`

__securityResult:__
- __ruleName__: `context_attributes.hunting_info.rule_name`
- __summary__: `attributes.threat_severity.level_description`
- __severityDetails__: `attributes.threat_severity.threat_severity_level`
- __urlBackToProduct__: Constructed using the rule ID: `https://yara-editor.virustotal.com/livehunt/{context_attributes.sources.0.id}`
- __ruleId__: `context_attributes.sources[0].id`
- __ruleLabels__:
  - __key__: "sources_label" (Hardcoded)
  - __value__: `context_attributes.sources[0].label`
  - __key__: "sources_type" (Hardcoded)
  - __value__: `context_attributes.sources[0].type`

__about:__
- __artifact__:
  - __ip__: `id`
  - __network__:
    - __asn__: `attributes.asn`
    - __ipSubnetRange__: `attributes.network`
  - __jarm__: `attributes.jarm`

## URL Object Mapping

[URL Object](https://gtidocs.virustotal.com/reference/url-object)

__metadata:__

- __productLogId__: `context_attributes.notification_id`
- __eventTimestamp__: `context_attributes.notification_date` 
- __eventType__: "GENERIC_EVENT" (Hardcoded)
- __vendorName__: "Google Cloud" (Hardcoded)
- __productName__: "IOC Stream" (Hardcoded)
- __productEventType__: `type` 
- __urlBackToProduct__: Constructed using the type and id: `https://www.virustotal.com/gui/{type}/{id}`
- __logType__: "GTI_IOC_STREAM" (Hardcoded)

__additional:__
- __malicious__: `last_analysis_stats.malicious`
- __suspicious__: `last_analysis_stats.suspicious`
- __undetected__: `last_analysis_stats.undetected`
- __harmless__: `last_analysis_stats.harmless`
- __timeout__: `last_analysis_stats.timeout`

__securityResult:__
- __summary__: `attributes.threat_severity.level_description` 
- __severityDetails__: `attributes.threat_severity.threat_severity_level`

__about:__
- __url__: `attributes.url``
