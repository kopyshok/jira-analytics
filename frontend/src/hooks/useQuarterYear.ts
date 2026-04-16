import { useSearchParams } from 'react-router';

const currentYear = new Date().getFullYear();
const currentQuarter = Math.ceil((new Date().getMonth() + 1) / 3);

export function useQuarterYear() {
  const [params] = useSearchParams();
  return {
    year: params.get('year') || String(currentYear),
    quarter: params.get('quarter') || String(currentQuarter),
  };
}
