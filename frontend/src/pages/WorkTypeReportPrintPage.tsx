import PrintView from '../components/work-type-report/PrintView';

/** Thin page wrapper — renders PrintView outside AppLayout (no sidebar/header). */
export default function WorkTypeReportPrintPage() {
  return <PrintView />;
}
