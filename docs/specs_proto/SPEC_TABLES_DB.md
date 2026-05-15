> ⚠️ **DOCUMENT HISTORIQUE / ARCHIVE — pré-refonte N1-N11 (16/05/2026)**
>
> Ce document décrit un état du projet qui a été remplacé par la refonte
> architecturale N1-N11 (11-14/05/2026) puis V12 SALLE (15-16/05).
> Conservé pour traçabilité historique. **Ne pas utiliser comme source
> de vérité pour l'état actuel du code.**
>
> Doc CURRENT (référence à jour) : `V2/database.py (schéma actuel)`.

---

# Tables SQLite (emails.db)

> **Dernière mise à jour** : 12/04/2026 (git)

*Extrait de CLAUDE.md — section Tables SQLite*

| Table | Usage |
|-------|-------|
| `threads` | Emails indexes (direction, subject, body, correspondent). Index: correspondent, created_at |
| `contact_profiles` | Profils comportementaux (register, ton, greeting, closing, etc.). Cle: email |
| `style_corrections` | Diffs propose vs envoye (apprentissage) + quality_impact (AMELIORATION/STYLE/DEGRADATION). Index: correspondent, created_at |
| `metrics` | Metriques d'envoi (action, importance, duration, direct_send). Index: action, created_at |
| `settings` | Parametres utilisateur (cle/valeur) : default_importance, user_name, last_milestone, onboarding_mail_count, writing_score, writing_level, writing_converged |
| `score_history` | Historique des scores par cycle de recalibrage (score, level, delta). Pour la detection de convergence |
| `echeances` | Echeances detectees par IA (date, description, type, priorite, correspondant, statut). Index: statut, date_echeance, correspondant |
| `folder_classifications` | Classements mails dans dossiers Outlook (folder_path, folder_id, contact_email, domain, subject_keywords, was_ai, was_corrected). Index: contact_email, domain, folder_path |
| `pj_classifications` | Classements PJ dans explorateur Windows (folder_path, contact_email, domain, subject_keywords, pj_type, original_name, renamed_to). Index: contact_email, domain |

**PRAGMA** : WAL mode, synchronous=NORMAL, cache_size=8MB. Connexion persistante par thread.
