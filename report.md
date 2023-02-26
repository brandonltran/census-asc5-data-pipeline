## Phase 1: Storing Census Data with Lambda and S3

### Step 1: Creating the Lambda Function
Using the AWS Management Console, I will navigate to the Lambda service and click `Create function`.
- Function template: `Authored from scratch`
- Function name: `extractCensusACS5`
- Runtime: `Python 3.8`
- Architecture: `x86_64`
- Permissions: `Create a new role with basic Lambda permissions`

### Step 2: Importing Dependencies
In this script, I will be using the `requests`, `pandas`, `boto3`, and `io` Python libraries.

> Note: while `boto3` and `io` are already included in this Lambda runtime, I will need to add layers in order to import the `requests` and `pandas` libraries. I can do this using the Lambda `extractCensusACS5` dashboard, and selecting `Add a layer`.

**Pandas**

First I will add the layer for `pandas`. Because AWS has a preconfigured layer for this library, I can include it by simply selecting it from the `AWS Layers` list. I will be selecting the following package:
- `AWSSDKPandas-Python38, Version 3`

**Requests**

To add the layer for `requests`, I will need to package the library manually and upload it to the layers directory.

Using AWS Cloudshell, I will create a directory for the library, install it using `pip3`, compress it and publish the layer using `aws lambda publish-layer-version`.

```console
mkdir requests_layer
cd requests_layer
sudo pip3 install requests -t .
zip -r9 requests.zip .
aws lambda publish-layer-version --layer-name requests --description "requests package" --zip-file fileb://requests.zip --compatible-runtimes python3.8
```

With the layer published, I can now add it as a layer under `Custom Layers`.

### Step 3: Creating the S3 Bucket

Using the AWS Management Console, I will navigate to S3 and create a new bucket `brandonltran-census-acs5-datasets`.

I will be using the following bucket policy to allow the Lambda function access to the bucket:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowPublicRead",
            "Effect": "Allow",
            "Principal": "*",
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::brandonltran-census-acs5-datasets/*"
        }
    ]
}
```

### Step 4: Writing the Python Function

Going back to the Lambda function, I can begin writing the script by importing the libraries mentioned in Step 2.

```python
import requests
import pandas as pd
import boto3
import io
```

Every Lambda function needs to be wrapped in a `lambda_handler` with parameters `event` and `context` as follows:
```python
def lambda_handler(event, context):
    
    # code
    
    return {
        'statusCode': 200,
        'body': print('Success')
    }
```
> Note that the end of the handler I have a return statement that contains `statusCode` and `body`. These are required in every Lambda function.

**Extracting Datasets From the Census.gov API**

In order to use the API, I can request an access token and store it in Lambda under `Configuration > Environment variables`.

The first part of the function will import this access token as `api_key` and define the basic parameters for the api call.
```python
# Import api key
api_key = os.environ['API_KEY']

# Define API parameters
base_url = "https://api.census.gov/data/"
dataset = "acs/acs5/profile"
state = "*"
 ```

Now I will define the main function `census_api` which will pass unique column IDs to use for each api call. Additionally, a `year` parameter will be passed to filter each dataset by year.
```python
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
```
The function does the following:
- Constructs an API call that includes the specified columns, states, and the access token
- Using the `year` parameter, it loops through each dataset for a given year and inserts it into a group
- The group of datasets is then concatenated into a single dataframe
- Finally, the dataframe is returned

**Loading Data in an Amazon S3 Bucket**

The next function will take a dataframe as an input and store it as a .csv file in an S3 bucket.
```python
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
```
This function takes three parameters:
- `dataset`, which defines the dataframe being stored
- `bucket_name`
- `filename`, which specifies the path and filename for the .csv

**Calling the Functions**

Finally, I can call the functions and extract the relevant datasets. For this project, I will be extracting 3 datasets:
- All states including their `state_id`
- Median household incomes per state
- Graduation rates per state

Each dataset will contain data points ranging from 2017-2018. They will be stored as individual .csv files in the S3 bucket `brandonltran-census-acs5-datasets`, sorted into subdirectories. Additionally, the columns in each dataframe will be renamed for readability.
```python
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
```

**Full Script**

```python
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
```
As explained above, if the function works properly, I should get `statusCode:200` and a printed output of the dataframes. See the output below:
> ```
> Response
> {
>   "statusCode": 200,
>   "body": null
> }
> 
> Function Logs
> START RequestId: 8e2fff28-b725-4708-b2e9-728c54ca9c44 Version: $LATEST
> 0           state state_id  year
> 1     Mississippi       28  2017
> 2        Missouri       29  2017
> 3         Montana       30  2017
> 4        Nebraska       31  2017
> 5          Nevada       32  2017
> ..            ...      ...   ...
> 48          Maine       23  2018
> 49       Maryland       24  2018
> 50  Massachusetts       25  2018
> 51       Michigan       26  2018
> 52      Minnesota       27  2018
> [104 rows x 3 columns] 0  median_household_income state_id  year
> 1                    42009       28  2017
> 2                    51542       29  2017
> 3                    50801       30  2017
> 4                    56675       31  2017
> 5                    55434       32  2017
> ..                     ...      ...   ...
> 48                   55425       23  2018
> 49                   81868       24  2018
> 50                   77378       25  2018
> 51                   54938       26  2018
> 52                   68411       27  2018
> [104 rows x 3 columns] 0  graduation_rate state_id  year
> 1             21.3       28  2017
> 2             28.2       29  2017
> 3             30.7       30  2017
> 4             30.6       31  2017
> 5             23.7       32  2017
> ..             ...      ...   ...
> 48            30.9       23  2018
> 49            39.6       24  2018
> 50            42.9       25  2018
> 51            28.6       26  2018
> 52            35.4       27  2018
> [104 rows x 3 columns]
> END RequestId: 8e2fff28-b725-4708-b2e9-728c54ca9c44
> REPORT RequestId: 8e2fff28-b725-4708-b2e9-728c54ca9c44	Duration: 7241.26 ms	Billed Duration: 7242 ms	Memory Size: 128 MB	Max Memory Used: 128 MB	Init Duration: 2342.14 ms
> ```

The data is now succesfully stored in Amazon S3.

## Phase 2: Dimensional Modeling with Amazon Athena

Let's recap and take a look at the current schemas for the extracted datasets.

![Census API Schema](census-api-schema.jpg)

I will be leveraging SQL and Amazon Athena to organize the data into materialized views based on the following dimensional star schema:

**Measures**
- Median Household Incomes
- Graduation Rates

**Dimensions**
- State
- Year

### Step 1: Importing Data into Amazon Athena

I'll start by creating a database for the data.
```sql
CREATE DATABASE censusacs5data
```

I can import each dataset from s3 into individual tables with the following queries.

**States**

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS censusacs5data.states (
  `state` string,
  `state_id` int,
  `year` int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'
WITH SERDEPROPERTIES (
    'field.delim' = ','
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://brandonltran-census-acs5-datasets/states'
TBLPROPERTIES (
    'classification' = 'csv',
    'skip.header.line.count' = '1'
);
```

**Median Household Incomes**

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS censusacs5data.median_household_incomes (
  `median_household_income` float,
  `state_id` int,
  `year` int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'
WITH SERDEPROPERTIES (
    'field.delim' = ','
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://brandonltran-census-acs5-datasets/median-household-incomes'
TBLPROPERTIES (
    'classification' = 'csv',
    'skip.header.line.count' = '1'
);
```

**Graduation Rates**

```sql
CREATE EXTERNAL TABLE IF NOT EXISTS censusacs5data.graduation_rates (
  `graduation_rate` float,
  `state_id` int,
  `year` int
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe'
WITH SERDEPROPERTIES (
    'field.delim' = ','
)
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat' OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat'
LOCATION 's3://brandonltran-census-acs5-datasets/graduation-rates'
TBLPROPERTIES (
    'classification' = 'csv',
    'skip.header.line.count' = '1'
);
```

These queries do the following:
- Creates a new table
- Imports relevant columns
- Specifies the delimiter
- Specifies the `INPUTFORMAT`
- Specifies the input is a .csv and the header rows should be skipped

### Step 2: Creating Views for Measures and Dimensions

With the data imported into tables with their original schemas, I can organize them into Athena Views based on the dimensional star schema I modeled.

**State Dimension**

```sql
CREATE OR REPLACE VIEW state_dim AS
SELECT DISTINCT state_id, state AS State
FROM censusacs5data.states;
```

**Year Dimension**

```sql
CREATE OR REPLACE VIEW year_dim AS
SELECT DISTINCT year AS Year
FROM censusacs5data.states;
```

**Median Household Income Measure**

```sql
CREATE OR REPLACE VIEW income_measure AS
SELECT DISTINCT median_household_income AS "Median Household Income", state_id, year AS year_id
FROM censusacs5data.median_household_incomes;
```

**Graduation Rate Measure**

```sql
CREATE OR REPLACE VIEW graduation_measure AS
SELECT DISTINCT graduation_rate AS "Graduation Rate", state_id, year AS year_id
FROM censusacs5data.graduation_rates;
```

The data is now organized into meausures and dimensions.

![Athena View Schema](athena-view-schema.jpg)

### Step 3: Joining Data in Fact of Measurement View

Finally, I will create a view to use with Quicksight based on `Median Household Income` vs. `Graduation Rate` by `State` and `Year`.

```sql
CREATE OR REPLACE VIEW income_vs_graduation_fact AS
SELECT income_measure."Median Household Income", graduation_measure."Graduation Rate", state_dim.State, year_dim.Year
FROM income_measure
JOIN graduation_measure ON income_measure.state_id = graduation_measure.state_id AND income_measure.year_id = graduation_measure.year_id
JOIN state_dim ON graduation_measure.state_id = state_dim.state_id
JOIN year_dim ON graduation_measure.year_id = year_dim.Year
```

## Phase 3: Data Visualization with Amazon Quicksight

### Step 1: Connecting AWS Quicksight to Athena Views

Now that the data is organized into materialized views in Athena, I can very easily create visualizations with Quicksight as follows:

1. Create a Dataset and select `Amazon Athena` as the source
2. Select database `censusacs5data`
3. Select `income_vs_graduation_fact` as the table

### Step 2: Creating a Visual

Let's do a basic exploratory analysis to examine the correlation between `Average Graduation Rates` and `Average Median Household Income` per state in the year 2018.

1. Create a sheet
2. Select `Graduation Rate` for the X-axis
3. Select `Median Household Income` for the Y-axis
4. Group/Color by `State`
5. Filter `Year` to include values `2018` only

### Average Graduation Rate and Average Median Household Income by State

![Average of Graduation Rate and Average of Median Household Income by State](median-household-income_vs_graduation-rates.jpg)

As expected, the data from the survey illustrates a strong correlation between graduation rates and median household incomes.

Although this outcome may not be surprising, the ability to group the averages by state offers unique insights that can drive meaningful action to improve education outcomes.

For instance, stakeholders can use this information to conduct further analysis of states with lower performance, identifying specific counties and schools with low graduation rates. With this knowledge, they can take proactive measures such as increasing funding for high schools in these areas to promote better educational outcomes.
