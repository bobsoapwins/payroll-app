# Washington State Payroll XML Generator

> [!CAUTION]
> This application is in a very early testing phase. Use with the assumption that outputs are wrong and that you should always double-check generations

This is a simple Python application that takes a very specifically formatted payroll spreadsheet (`.xlsx`) and turns it into `XML` code. It then runs that output against [schema.xsd](https://github.com/bobsoapwins/payroll-app/blob/main/schema.xsd), which is a validator from the Washington State Department of Labor and Industries. This allows companies who use this exact format of payroll spreadsheet and this exact method of submitting `XML` code to the [L&I website](https://lni.wa.gov/) to have an easier job converting the spreadsheet.

## Overview

Manually formatting payroll data to meet state regulatory standards can be tedious and prone to error. This tool bridges the gap between internal spreadsheets and state compliance requirements.
It reads your structured payroll spreadsheet file, transforms the data into the exact `XML` schema mandated by the state, and automatically validates the output against the official L&I XSD schema to ensure flawless submissions.

## Key Features

- Generation and validation is fast, and very easy

- The project compares the validator schema and the generated `XML` code, ensuring the generated code is valid

- Errors in spreadsheet formatting that contradict the validator schema throws errors so you can easily identify problems

- This application is much faster than manual data entry, and is less prone to errors
