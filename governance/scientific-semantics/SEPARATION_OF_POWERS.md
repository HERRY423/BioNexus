# Technical, commercial, and certification separation

## Constitutional allocation

| Reserved power | Technical — SSC | Commercial operators | Certification / assurance |
|---|:---:|:---:|:---:|
| Define semantic meaning and namespace | Owns | Prohibited | Prohibited |
| Approve registry/schema release | Owns | Prohibited | May comment only |
| Define public conformance test specification | Owns | Prohibited | Consumes frozen version |
| Fund infrastructure and events | May request | Owns | Must disclose |
| Operate products and set prices | Prohibited | Owns | Prohibited |
| Manage trademarks under published policy | Consulted | Owns | Licensed use only |
| Recognize eligible CABs | Prohibited | Prohibited | Scheme oversight owns |
| Assess an implementation | Prohibited | Prohibited | Independent CAB owns |
| Issue, suspend, or revoke a certificate | Prohibited | Prohibited | Independent CAB owns |
| Hear technical appeal | Owns independent panel | Prohibited | Prohibited |
| Hear certification appeal | Prohibited | Prohibited | Separate assurance panel |

## Firewalls

1. A person may advise more than one branch, but may not vote in technical and
   certification decisions concerning the same implementation or release.
2. A commercial operator may fund tests but cannot select assessors, alter
   results, suppress failures, or condition funding on a technical vote.
3. The SSC publishes conformance specifications and fixtures but does not
   determine whether a named product receives a certificate.
4. A CAB may identify ambiguity in the standard through an RFC, but cannot
   privately reinterpret a requirement during assessment.
5. Certification fees are paid to the CAB or disclosed scheme operator, never
   to an SSC member for a decision involving that applicant.
6. BioNexus-authored software is evaluated under the same frozen release and
   may not use a BioNexus-controlled CAB.
7. Marketing terms such as “certified”, “approved”, “endorsed”, or badge marks
   require an active, independently issued, publicly verifiable certificate.

## Failure state

If any firewall cannot be demonstrated, certification is suspended and the
public state is `NOT_ASSESSED`. Technical test output may still be published as
a development diagnostic, but it cannot be converted into a badge.
