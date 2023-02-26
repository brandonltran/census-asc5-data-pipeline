import requests
import pandas as pd
import boto3
import io
import os

def lambda_handler(event, context):
    
    # Import api key
    api_key = os.environ['API_KEY']
    
    # Define API parameters
    base_url = "https://api.census.gov/data/"
    dataset = "acs/acs5/profile"
    state = "*"
    
    def census_api(columns,years):
        
        # Create an empty list to store all datasets
        datasets = []
        
        # Loop through each `year` parameter
        for year in years:
            
            # Use requests to make an API call for current year in loop
            url = f"{base_url}{year}/{dataset}?get={columns}&for=state:{state}&key={api_key}"
            response = requests.get(url)
            
            # Store response json into dataframe
            this_dataset = pd.DataFrame(response.json())
            
            # Set column names
            this_dataset.columns = this_dataset.iloc[0]
            this_dataset = this_dataset[1:]
            
            # Add column to store `year` parameter
            this_dataset['year'] = year
            
            # Append this dataset to the datasets list
            datasets.append(this_dataset)
        
        # Concatenate datasets for each year into a dataframe
        all_datasets = pd.concat(datasets)
        
        return all_datasets
    
    def s3_load(dataset,bucket_name,filename):
        
        # Initialize boto3 client
        s3 = boto3.client('s3')
        
        # Convert dataset input to .csv using csv buffer
        buffer = io.StringIO()
        dataset.to_csv(buffer, encoding="UTF-8", index=False)
        
        # Upload to s3
        s3.put_object(
            Bucket=bucket_name,
            Key=filename,
            Body=buffer.getvalue(),
            ContentType='text/csv',
            ContentEncoding='UTF-8'
        )
    
    # Return datasets
    states = census_api('NAME',['2017','2018'])
    median_household_incomes = census_api('DP03_0062E',['2017','2018'])
    graduation_rates = census_api('DP02_0067PE',['2017','2018'])
        
    # Rename columns for readability
    states = states.rename(columns={
        "NAME": "state",
        "state": "state_id"
    })
        
    median_household_incomes = median_household_incomes.rename(columns={
        "DP03_0062E": "median_household_income",
        "state": "state_id"
    })
        
    graduation_rates = graduation_rates.rename(columns={
        "DP02_0067PE": "graduation_rate",
        "state": "state_id"
    })
    
    # Load dataset into s3
    s3_load(states,'brandonltran-census-acs5-datasets','states/census_acs5_states.csv')
    s3_load(median_household_incomes,'brandonltran-census-acs5-datasets','median-household-incomes/census_acs5_median_household_incomes.csv')
    s3_load(graduation_rates,'brandonltran-census-acs5-datasets','graduation-rates/census_acs5_graduation_rates.csv')
    
    # Function output
    return {
        'statusCode': 200,
        'body': print(states,median_household_incomes,graduation_rates)
    }
