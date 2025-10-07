function short_squeeze_screener
% MATLAB Short Squeeze Stock Screener
% This script loads financial data, then runs two separate analyses:
% 1. A standard screen for top candidates under $5.
% 2. A progressive, adaptive screen for sub-dollar candidates.

clc;
clear;
close all;

% --- 1. LOAD DATA ---
allData = loadData();
if isempty(allData)
    return; % Exit if data loading fails
end

% --- 2. RUN STANDARD SCREENER ---
disp('--- RUNNING STANDARD SCREENER (UNDER $5) ---');
standardParams.priceLimit = 5;
standardParams.minShortInterest = 20;
standardParams.minDaysToCover = 3;
standardParams.maxFloatShares = 100e6;
standardParams.numToShow = 15;
standardParams.title = '--- FINAL RESULTS: TOP SHORT SQUEEZE CANDIDATES (Under $5) ---';
runScreener(allData, standardParams);

% --- 3. RUN PROGRESSIVE SUB-DOLLAR SCREENER ---
fprintf('\n\n'); % Add space for readability
disp('--- RUNNING PROGRESSIVE SUB-DOLLAR SCREENER (UNDER $1) ---');
runProgressiveScreener(allData, 5); % Find top 5 candidates

end

% --- Main Screener Logic Function (Standard) ---
function runScreener(data, params)
    % This function runs a screen with one fixed set of parameters.
    
    fprintf('Applying filters:\n');
    fprintf('- Price < $%.2f\n', params.priceLimit);
    fprintf('- Short Interest > %.2f%%\n', params.minShortInterest);
    fprintf('- Days to Cover > %.2f\n', params.minDaysToCover);
    fprintf('- Float Shares < %.0fM\n\n', params.maxFloatShares / 1e6);

    candidates = data(...
        data.CurrentPrice < params.priceLimit & ...
        data.CurrentPrice > 0 & ...
        data.ShortInterestPercent > params.minShortInterest & ...
        data.DaysToCover > params.minDaysToCover & ...
        data.Float_Shares < params.maxFloatShares, :);

    if isempty(candidates)
        fprintf('No stocks passed the screening criteria for this set.\n');
        return;
    end

    fprintf('%d stocks passed the filters for this set.\n', height(candidates));
    scoreAndDisplay(candidates, params);
end

% --- CORRECTED: Progressive Screener Logic Function ---
function runProgressiveScreener(data, numToShow)
    % This function starts with strict filters and progressively LOOSENS
    % them until it finds at least `numToShow` candidates.
    
    % --- DIAGNOSTIC STEP with SCORING ---
    subDollarPool = data(data.CurrentPrice < 1 & data.CurrentPrice > 0, :);
    if isempty(subDollarPool)
        fprintf('DIAGNOSTIC: No stocks under $1 were found in the provided CSV file.\n');
    else
        fprintf('DIAGNOSTIC: Found %d stocks under $1. Scoring and ranking them...\n', height(subDollarPool));
        
        % Calculate Squeeze Score for the entire sub-dollar pool
        if height(subDollarPool) > 1
            normSI = (subDollarPool.ShortInterestPercent - min(subDollarPool.ShortInterestPercent)) / (max(subDollarPool.ShortInterestPercent) - min(subDollarPool.ShortInterestPercent));
            normDTC = (subDollarPool.DaysToCover - min(subDollarPool.DaysToCover)) / (max(subDollarPool.DaysToCover) - min(subDollarPool.DaysToCover));
            normFloat = 1 - ((subDollarPool.Float_Shares - min(subDollarPool.Float_Shares)) / (max(subDollarPool.Float_Shares) - min(subDollarPool.Float_Shares)));
            
            normSI(isnan(normSI)) = 0.5; % Use a neutral value if all are the same
            normDTC(isnan(normDTC)) = 0.5;
            normFloat(isnan(normFloat)) = 0.5;

            weightSI = 0.50; weightDTC = 0.30; weightFloat = 0.20;
            subDollarPool.SqueezeScore = (normSI * weightSI + normDTC * weightDTC + normFloat * weightFloat) * 100;
        else
            subDollarPool.SqueezeScore = 50; % Assign a default score if only one stock
        end
        
        % Sort the diagnostic pool by score to show the best ones first
        subDollarPool = sortrows(subDollarPool, 'SqueezeScore', 'descend');
        
        % Display a simplified table for review, now including the score and volume
        disp(subDollarPool(:, {'Ticker', 'SqueezeScore', 'CurrentPrice', 'ShortInterestPercent', 'DaysToCover', 'Float_Shares', 'AvgVolume10Day'}));
    end
    fprintf('--------------------------------------------------------------------------\n');
    
    candidates = [];
    maxIterations = 20; % Safety break to prevent infinite loops
    iteration = 1;
    
    % Initial (strict) parameters
    currentSI = 25;
    currentDTC = 4;
    currentFloat = 100e6; 

    fprintf('Starting progressive search for sub-$1 stocks...\n');
    
    % CORRECTED LOOP: Continue until we find enough candidates or hit the limit.
    while height(candidates) < numToShow && iteration <= maxIterations
        fprintf('Attempt %d: SI > %.1f%%, DTC > %.1f, Float < %.0fM\n', iteration, currentSI, currentDTC, currentFloat/1e6);
        
        % Apply current filters to the pre-filtered sub-dollar pool
        candidates = subDollarPool(...
            subDollarPool.ShortInterestPercent > currentSI & ...
            subDollarPool.DaysToCover > currentDTC & ...
            subDollarPool.Float_Shares < currentFloat, :);
        
        % If not enough candidates were found, LOOSEN the filters for the next attempt.
        if height(candidates) < numToShow
            currentSI = max(5, currentSI - 1);           % Decrease required SI (min 5%)
            currentDTC = max(0.5, currentDTC - 0.2);     % Decrease required DTC (min 0.5)
            currentFloat = currentFloat + 25e6;          % Increase the max float allowed
        end
        
        iteration = iteration + 1;
    end
    
    if isempty(candidates)
        fprintf('\nNo stocks passed the progressive screening criteria, even at the loosest settings.\n');
        return;
    end
    
    fprintf('\nFound %d potential candidates after %d attempts.\n', height(candidates), iteration - 1);
    
    % Now score and display the results we found
    params.numToShow = numToShow;
    params.title = '--- FINAL RESULTS: TOP 5 SUB-DOLLAR CANDIDATES (Progressive Search) ---';
    scoreAndDisplay(candidates, params);
end


% --- Universal Scoring and Display Function ---
function scoreAndDisplay(candidates, params)
    % This function takes a table of candidates, scores them, and displays the top results.
    
    % --- Calculate Squeeze Score ---
    % Recalculate score based only on the final candidates for the most accurate relative ranking
    if height(candidates) > 1
        normSI = (candidates.ShortInterestPercent - min(candidates.ShortInterestPercent)) / (max(candidates.ShortInterestPercent) - min(candidates.ShortInterestPercent));
        normDTC = (candidates.DaysToCover - min(candidates.DaysToCover)) / (max(candidates.DaysToCover) - min(candidates.DaysToCover));
        normFloat = 1 - ((candidates.Float_Shares - min(candidates.Float_Shares)) / (max(candidates.Float_Shares) - min(candidates.Float_Shares)));
        
        normSI(isnan(normSI)) = 0.5;
        normDTC(isnan(normDTC)) = 0.5;
        normFloat(isnan(normFloat)) = 0.5;

        weightSI = 0.50; weightDTC = 0.30; weightFloat = 0.20;
        candidates.SqueezeScore = (normSI * weightSI + normDTC * weightDTC + normFloat * weightFloat) * 100;
    else
        candidates.SqueezeScore = 50; % Assign a default score if only one stock
    end

    % --- Sort and Display Top Candidates ---
    sortedCandidates = sortrows(candidates, 'SqueezeScore', 'descend');
    topCandidates = sortedCandidates(1:min(params.numToShow, height(sortedCandidates)), :);

    disp(params.title);
    displayTable = table(...
        topCandidates.Ticker, ...
        round(topCandidates.SqueezeScore, 1), ...
        topCandidates.ShortInterestPercent, ...
        topCandidates.DaysToCover, ...
        cellfun(@formatMarketNumber, num2cell(topCandidates.Float_Shares), 'UniformOutput', false), ...
        cellfun(@formatMarketNumber, num2cell(topCandidates.MarketCap), 'UniformOutput', false), ...
        cellfun(@formatMarketNumber, num2cell(topCandidates.AvgVolume10Day), 'UniformOutput', false), ... % ADDED
        topCandidates.CurrentPrice, ...
        'VariableNames', {'Ticker', 'SqueezeScore', 'ShortInterest(%)', 'DaysToCover', 'Float', 'MarketCap', 'AvgVolume', 'CurrentPrice'}); % ADDED
    disp(displayTable);
end


% --- Data Loading Function ---
function data = loadData()
    % This function finds and loads the most recent CSV file.
    filePattern = fullfile(pwd, 'full_market_data_*.csv');
    fileList = dir(filePattern);
    if isempty(fileList)
        error('CRITICAL ERROR: No data file found. Please run the Python script first.');
    end
    [~, idx] = sort([fileList.datenum], 'descend');
    latestFile = fullfile(pwd, fileList(idx(1)).name);
    fprintf('Loading the most recent data file: %s\n', latestFile);
    opts = detectImportOptions(latestFile);
    opts = setvartype(opts, 'Ticker', 'string');
    data = readtable(latestFile, opts);
    fprintf('Successfully loaded data for %d stocks.\n\n', height(data));
end

% --- Helper Function for Formatting ---
function formattedStr = formatMarketNumber(n)
    % Formats large numbers into a readable string (e.g., 1.25B, 250.50M).
    if n >= 1e9
        formattedStr = sprintf('%.2fB', n / 1e9);
    elseif n >= 1e6
        formattedStr = sprintf('%.2fM', n / 1e6);
    elseif n >= 1e3
        formattedStr = sprintf('%.2fK', n / 1e3);
    else
        formattedStr = sprintf('%.2f', n);
    end
end

