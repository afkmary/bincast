// dashboard/src/components/Logo.tsx
import logoUrl from "../assets/longbincastlogo.png";

export default function Logo() {
  return (
    <div className="brand">
      <img src={logoUrl} alt="bincast" className="brand-logo" />
      <span className="brand-divider" aria-hidden="true" />
      <span className="brand-sub">Dashboard</span>
    </div>
  );
}