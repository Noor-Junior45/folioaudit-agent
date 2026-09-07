// config/amcs.js

export const AMCS = [
  {
    key: "sbi",
    name: "SBI Mutual Fund",
    baseUrl: "https://www.sbimf.com/portfolios",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "icici_pru",
    name: "ICICI Prudential Mutual Fund",
    baseUrl:
      "https://www.icicipruamc.com/news-and-media/downloads?currentTabFilter=OtherSchemeDisclosures%26%26subCatTabFilter=Monthly%20Portfolio%20Disclosures",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "hdfc",
    name: "HDFC Mutual Fund",
    baseUrl:
      "https://www.hdfcfund.com/statutory-disclosure/portfolio/monthly-portfolio",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "nippon_india",
    name: "Nippon India Mutual Fund",
    baseUrl:
      "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "kotak",
    name: "Kotak Mutual Fund",
    baseUrl: "https://www.kotakmf.com/Information/portfolios",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "aditya_birla",
    name: "Aditya Birla Sun Life Mutual Fund",
    baseUrl:
      "https://mutualfund.adityabirlacapital.com/forms-and-downloads/portfolio",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "uti",
    name: "UTI Mutual Fund",
    baseUrl:
      "https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "axis",
    name: "Axis Mutual Fund",
    baseUrl: "https://www.axismf.com/statutory-disclosures",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "mirae_asset",
    name: "Mirae Asset Mutual Fund",
    baseUrl: "https://www.miraeassetmf.co.in/downloads/portfolio",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "dsp",
    name: "DSP Mutual Fund",
    baseUrl:
      "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "whiteoak",
    name: "WhiteOak Capital Mutual Fund",
    baseUrl:
      "https://mf.whiteoakamc.com/regulatory-disclosures/scheme-portfolios",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  },
  {
    key: "motilal_oswal",
    name: "Motilal Oswal Mutual Fund",
    baseUrl:
      "https://www.motilaloswalmf.com/downloads/scheme-portfolio-details",
    sourceType: "dynamic_page",
    expectedFormats: ["xlsx", "xls", "pdf"],
    frequency: "monthly"
  }
];
