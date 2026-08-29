import type { SVGProps } from "react";

const defaults = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8 };

export function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.8-3.8"/></svg>;
}

export function HistoryIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>;
}

export function CompaniesIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16M2 21h20M8 7h4M8 11h4M8 15h4M18 9h2v12"/></svg>;
}

export function CoverageIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/><path d="m4 7 6-4 6 7 5-5"/></svg>;
}

export function UserIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>;
}

export function RefreshIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M20 7h-5V2M4 17h5v5"/><path d="M18.5 9A7 7 0 0 0 6 5.5L4 7m2 8a7 7 0 0 0 12 3l2-2"/></svg>;
}

export function ExternalIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></svg>;
}

export function ChevronDownIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="m6 9 6 6 6-6" /></svg>;
}

export function ChevronLeftIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="m15 18-6-6 6-6" /></svg>;
}

export function ChevronRightIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="m9 18 6-6-6-6" /></svg>;
}

export function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M6 6l12 12M18 6 6 18" /></svg>;
}

export function StopIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><rect x="6" y="6" width="12" height="12" rx="1" /></svg>;
}

export function MenuIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
}

export function LogoutIcon(props: SVGProps<SVGSVGElement>) {
  return <svg {...defaults} {...props}><path d="M10 5H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h5M14 8l4 4-4 4M8 12h10" /></svg>;
}
