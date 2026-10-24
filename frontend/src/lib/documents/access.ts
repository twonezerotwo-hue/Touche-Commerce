/** Who may generate customer-facing documents: traders and finance reviewers. */
export function canGenerateDocuments(
  company: { permissions: readonly string[] } | null | undefined,
): boolean {
  const permissions = company?.permissions ?? [];
  return permissions.includes("trade.write") || permissions.includes("finance.approve");
}
