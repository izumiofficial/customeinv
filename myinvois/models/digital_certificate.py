import base64
import os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from odoo import api, fields, models, _
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, BestAvailableEncryption
from odoo.exceptions import UserError, ValidationError
import pytz
import json
from hashlib import sha256
from datetime import timedelta, datetime, date, timezone


class ResCompany(models.Model):
    _inherit = "res.company"

    def sign_digest(self, hashdata):
        """Sign the document hash with the private key."""
        try:
            f = open("/tmp/myinvois/"+self.name+".pem", "r")
            cert_pem=f.read()
            if hashdata is None:
                raise ValueError("hashdata cannot be None")
            if cert_pem is None:
                raise ValueError("cert_pem cannot be None")
            cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            # print(cert.issuer)
            pass_file= self.my_invois_p12_pin
            private_key = serialization.load_pem_private_key(
                cert_pem.encode(),
                password=pass_file.encode(),
                backend=default_backend()
            )
            
            if private_key is None or not isinstance(private_key, rsa.RSAPrivateKey):
                raise ValueError("The certificate does not contain an RSA private key.")
            
            try:
                signed_data = private_key.sign(
                    hashdata,
                    padding.PKCS1v15(),
                    hashes.SHA256()        
                )
                base64_bytes = base64.b64encode(signed_data)
                base64_string = base64_bytes.decode("ascii")
            except Exception as e:
                raise ValidationError(f"An error occurred while signing the data.: {str(e)}")
            
            return base64_string
        except Exception as e:
            raise ValidationError(f"Error in sign data: {str(e)}")

    def convert_json_to_base64(self, json_data):
        json_string = json.dumps(json_data, separators=(',', ':'), sort_keys=True)
        json_bytes = json_string.encode("utf-8")
        base64_bytes = base64.b64encode(json_bytes)
        base64_string = base64_bytes.decode("utf-8")
        return base64_string
            
    def hash_json_data(self, data):
        hashed = sha256(json.dumps(data, separators=(',', ':'), sort_keys=True).encode('utf8')).hexdigest()
        return hashed
    
    def encode_base64(self, data):
        return base64.b64encode(data).decode('utf-8')

    def calculate_digest(self, data):
        """
        Calculate the SHA-256 digest of the canonicalized data.
        """
        return sha256(data).digest()
    
    def signed_properties_hash(self, single_line_xml):
        try:

            # single_line_xml = f'''<xades:SignedProperties Id="id-xades-signed-props" xmlns:xades="http://uri.etsi.org/01903/v1.3.2#"><xades:SignedSignatureProperties><xades:SigningTime>{signing_time}</xades:SigningTime><xades:SigningCertificate><xades:Cert><xades:CertDigest><ds:DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256" xmlns:ds="http://www.w3.org/2000/09/xmldsig#"></ds:DigestMethod><ds:DigestValue xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{cert_digest}</ds:DigestValue></xades:CertDigest><xades:IssuerSerial><ds:X509IssuerName xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{formatted_issuer_name}</ds:X509IssuerName><ds:X509SerialNumber xmlns:ds="http://www.w3.org/2000/09/xmldsig#">{x509_serial_number}</ds:X509SerialNumber></xades:IssuerSerial></xades:Cert></xades:SigningCertificate></xades:SignedSignatureProperties></xades:SignedProperties>'''
            prop_cert_hash = sha256(single_line_xml.encode('utf-8')).digest()
            prop_cert_base64 = base64.b64encode(prop_cert_hash).decode('utf-8')
            # print(f"SHA-256 Hash in Base64 (propCert): {prop_cert_base64}")
            return prop_cert_base64
        except Exception as e:
            raise ValidationError(f"Error signed properties hash: {str(e)}")

    def sign_document(self, payload, invoice_id=None):
        # https://sdk.myinvois.hasil.gov.my/signature-creation-json/
        # step 4 calculate cert digest sha256
        certificate_base64, formatted_issuer_name,  x509_serial_number ,cert_digest ,signing_time = self.load_keystore()
        # step 1 transform the document
        canonical_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
        # step 2 calculate document digest sha256
        doc_sha256 = self.calculate_digest(canonical_json)
        doc_digest = self.encode_base64(doc_sha256)
        # step 3 sign document sha256 with certificate
        signature = self.sign_digest(canonical_json)
        # assign digital signature to field
        if invoice_id:
            invoice_id.my_invois_digital_signature = cert_digest
        
        
        
        # step 5 populate signed property
        signed_properties = [
                                {
                                    "Id": "id-xades-signed-props",
                                    "SignedSignatureProperties": [
                                        {
                                            "SigningTime": [
                                                {
                                                    "_": signing_time
                                                }
                                            ],
                                            "SigningCertificate": [
                                                {
                                                    "Cert": [
                                                        {
                                                            "CertDigest": [
                                                                {
                                                                    "DigestMethod": [
                                                                        {
                                                                            "_": "",
                                                                            "Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"
                                                                        }
                                                                    ],
                                                                    "DigestValue": [
                                                                        {
                                                                            "_": cert_digest
                                                                        }
                                                                    ]
                                                                }
                                                            ],
                                                            "IssuerSerial": [
                                                                {
                                                                    "X509IssuerName": [
                                                                        {
                                                                            "_": formatted_issuer_name
                                                                        }
                                                                    ],
                                                                    "X509SerialNumber": [
                                                                        {
                                                                            "_": x509_serial_number
                                                                        }
                                                                    ]
                                                                }
                                                            ]
                                                        }
                                                    ]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                            
        # Step 6: Generate Signed Properties digest (add outer content)
        outer_signed_props = {
            "Target": "signature",
            "SignedProperties": signed_properties
        }
        signed_properties_json = json.dumps(outer_signed_props, separators=(',', ':'), sort_keys=True)
        prop_cert_base64 = self.signed_properties_hash(signed_properties_json)
        sign_element = { "UBLExtensions": [
            {
                "UBLExtension": [
                    {
                        "ExtensionURI": [
                            {
                                "_": "urn:oasis:names:specification:ubl:dsig:enveloped:xades"
                            }
                        ],
                        "ExtensionContent": [
                            {
                                "UBLDocumentSignatures": [
                                    {
                                        "SignatureInformation": [
                                            {
                                                "ID": [
                                                    {
                                                        "_": "urn:oasis:names:specification:ubl:signature:1"
                                                    }
                                                ],
                                                "ReferencedSignatureID": [
                                                    {
                                                        "_": "urn:oasis:names:specification:ubl:signature:Invoice"
                                                    }
                                                ],
                                                "Signature": [
                                                    {
                                                        "Id": "signature",
                                                        "Object": [
                                                            {
                                                                "QualifyingProperties": [
                                                                    {
                                                                        "Target": "signature",
                                                                        "SignedProperties": signed_properties
                                                                    }
                                                                ]
                                                            }
                                                        ],
                                                        "KeyInfo": [
                                                            {
                                                                "X509Data": [
                                                                    {
                                                                        "X509Certificate": [
                                                                            {
                                                                                "_": certificate_base64
                                                                            }
                                                                        ],
                                                                        # "X509SubjectName": [
                                                                        #     {
                                                                        #         "_": self.extract_issuer(str(certificate.subject))
                                                                        #     }
                                                                        # ],
                                                                        # "X509IssuerSerial": [
                                                                        #     {
                                                                        #         "X509IssuerName": [
                                                                        #             {
                                                                        #                 "_": formatted_issuer_name
                                                                        #             }
                                                                        #         ],
                                                                        #         "X509SerialNumber": [
                                                                        #             {
                                                                        #                 "_": x509_serial_number
                                                                        #             }
                                                                        #         ]
                                                                        #     }
                                                                        # ]
                                                                    }
                                                                ]
                                                            }
                                                        ],
                                                        "SignatureValue": [
                                                            {
                                                                "_": signature
                                                            }
                                                        ],
                                                        "SignedInfo": [
                                                            {
                                                                "SignatureMethod": [
                                                                    {
                                                                        "_": "",
                                                                        "Algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
                                                                    }
                                                                ],
                                                                "Reference": [
                                                                    {
                                                                        "Type": "http://uri.etsi.org/01903/v1.3.2#SignedProperties",
                                                                        "URI": "#id-xades-signed-props",
                                                                        "DigestMethod": [
                                                                            {
                                                                                "_": "",
                                                                                "Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"
                                                                            }
                                                                        ],
                                                                        "DigestValue": [
                                                                            {
                                                                                "_": prop_cert_base64
                                                                            }
                                                                        ]
                                                                    },
                                                                    {
                                                                        "Type": "",
                                                                        "URI": "",
                                                                        "DigestMethod": [
                                                                            {
                                                                                "_": "",
                                                                                "Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"
                                                                            }
                                                                        ],
                                                                        "DigestValue": [
                                                                            {
                                                                                "_": doc_digest
                                                                            }
                                                                        ]
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ],

        "Signature": [
                {
                    "ID": [
                        {
                            "_": "urn:oasis:names:specification:ubl:signature:Invoice"
                        }
                    ],
                    "SignatureMethod": [
                        {
                            "_": "urn:oasis:names:specification:ubl:dsig:enveloped:xades"
                        }
                    ]
                }
            ]
        }
        return sign_element

    def load_keystore(self):
        p12_binary = self.my_invois_p12
        p12_password = self.my_invois_p12_pin
        # pfx_path = '/home/kresna/git/PCI_ODOO_(MALAYSIA)_SDN._BHD..p12'
        
        pfx_password = p12_password
        pem_output_path = "/tmp/myinvois/"+self.name+".pem"
        pem_encryption_password = pfx_password.encode()   
        os.makedirs(os.path.dirname(pem_output_path), exist_ok=True)
        pfx_data = base64.b64decode(p12_binary)
        private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
            pfx_data, pfx_password.encode(), backend=default_backend()
        )

        with open(pem_output_path, "wb") as pem_file:
            if private_key:
                pem_file.write(private_key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.PKCS8,  
                    encryption_algorithm=BestAvailableEncryption(pem_encryption_password) 
                ))

            if certificate:
                certificate_base64 = base64.b64encode(certificate.public_bytes(Encoding.DER)).decode("utf-8")
                pem_file.write(certificate.public_bytes(Encoding.PEM))
                x509_issuer_name = formatted_issuer_name = certificate.issuer.rfc4514_string()
                formatted_issuer_name =x509_issuer_name.replace(",", ", ")
                x509_serial_number = certificate.serial_number
                cert_digest = base64.b64encode(certificate.fingerprint(hashes.SHA256())).decode("utf-8")
                # TO DO : save certificate to database
                signing_time =  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            
            if additional_certificates:
                for cert in additional_certificates:
                    pem_file.write(cert.public_bytes(Encoding.PEM))
            return  certificate_base64, formatted_issuer_name,  x509_serial_number ,cert_digest ,signing_time
        

