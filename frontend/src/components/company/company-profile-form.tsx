"use client";

import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  saveCompanyProfile,
  type CompanyProfile,
  type CompanyProfileValues,
} from "@/lib/company/client";
import { useLocale } from "@/lib/i18n/locale-provider";
import type { MessageKey } from "@/lib/i18n/messages";

type FieldName = keyof CompanyProfileValues;

const SECTIONS: readonly { title: MessageKey; fields: readonly [FieldName, MessageKey][] }[] = [
  {
    title: "profileSectionLegal",
    fields: [
      ["legal_name", "profileLegalName"],
      ["tax_office", "profileTaxOffice"],
      ["tax_number", "profileTaxNumber"],
      ["address", "profileAddress"],
      ["city", "profileCity"],
      ["postal_code", "profilePostalCode"],
    ],
  },
  {
    title: "profileSectionContact",
    fields: [
      ["phone", "profilePhone"],
      ["email", "profileEmail"],
      ["website", "profileWebsite"],
    ],
  },
  {
    title: "profileSectionBank",
    fields: [
      ["bank_name", "profileBankName"],
      ["iban", "profileIban"],
      ["swift_bic", "profileSwift"],
    ],
  },
];

const MISSING_LABEL: Record<string, MessageKey> = {
  legal_name: "profileLegalName",
  tax_number: "profileTaxNumber",
  address: "profileAddress",
};

function initialValues(profile: CompanyProfile): Record<FieldName, string> {
  const values = {} as Record<FieldName, string>;
  for (const section of SECTIONS) {
    for (const [name] of section.fields) values[name] = profile[name] ?? "";
  }
  return values;
}

export function CompanyProfileForm({
  profile,
  csrfToken,
  canEdit,
}: {
  profile: CompanyProfile;
  csrfToken: string;
  canEdit: boolean;
}) {
  const { t } = useLocale();
  const [current, setCurrent] = useState(profile);
  const [values, setValues] = useState(() => initialValues(profile));
  const [pending, setPending] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<{ message: string; fields: string[] } | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setSaved(false);
    setError(null);
    const payload = Object.fromEntries(
      Object.entries(values).map(([name, value]) => [name, value.trim() === "" ? null : value]),
    ) as CompanyProfileValues;
    const result = await saveCompanyProfile(payload, current.version, csrfToken);
    setPending(false);
    if (result.ok) {
      setCurrent(result.profile);
      setValues(initialValues(result.profile));
      setSaved(true);
      return;
    }
    setError({
      message: result.conflict ? t("profileConflict") : `${result.message} (${result.code})`,
      fields: result.fields,
    });
  }

  const missing = current.missing_essentials.map((field) => t(MISSING_LABEL[field])).join(", ");

  return (
    <form onSubmit={onSubmit} className="space-y-6" noValidate>
      {!canEdit ? <Alert variant="info">{t("profileReadOnly")}</Alert> : null}
      <p role="status" className="text-[12px] text-mist-400">
        {current.missing_essentials.length > 0
          ? t("profileMissing", { fields: missing })
          : t("profileComplete")}
      </p>

      {SECTIONS.map((section) => (
        <fieldset key={section.title} className="panel space-y-4 p-5">
          <legend className="eyebrow px-1">{t(section.title)}</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            {section.fields.map(([name, label]) => (
              <div
                key={name}
                className={name === "address" ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"}
              >
                <Label htmlFor={`profile-${name}`}>{t(label)}</Label>
                <Input
                  id={`profile-${name}`}
                  value={values[name]}
                  disabled={!canEdit || pending}
                  aria-invalid={error?.fields.includes(name) ? true : undefined}
                  onChange={(event) =>
                    setValues((prev) => ({ ...prev, [name]: event.target.value }))
                  }
                  autoComplete="off"
                />
              </div>
            ))}
          </div>
        </fieldset>
      ))}

      {error ? <Alert variant="danger">{error.message}</Alert> : null}
      {saved ? <Alert variant="success">{t("profileSaved")}</Alert> : null}

      {canEdit ? (
        <Button type="submit" disabled={pending}>
          {pending ? t("profileSaving") : t("profileSave")}
        </Button>
      ) : null}
    </form>
  );
}
