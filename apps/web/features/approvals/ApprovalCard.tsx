export function ApprovalCard({
  headline,
  flagged,
  onDecide,
}: {
  headline: string;
  flagged: string[];
  onDecide: (decision: "approve" | "reject") => void;
}) {
  return (
    <article className="card">
      <h2>{headline}</h2>
      {flagged.length > 0 ? <p className="flagged">Copied from untrusted input: {flagged.join(", ")}</p> : null}
      <button type="button" onClick={() => onDecide("approve")}>
        Approve
      </button>
      <button type="button" onClick={() => onDecide("reject")}>
        Reject
      </button>
    </article>
  );
}
