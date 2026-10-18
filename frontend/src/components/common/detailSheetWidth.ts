import { createContext, useContext } from 'react';

/** Ширина тела открытой панели подробностей, px; вне панели — 0. */
export const DetailSheetWidthContext = createContext(0);

/**
 * Содержимое панели знает свою ширину: широкая — раскладывает колонками и
 * разворачивает секции, узкая — ставит их одну под другой.
 */
export const useDetailSheetWidth = () => useContext(DetailSheetWidthContext);
