function [idx,medoidsIndex] = kmeansClustering(data)
    data = data';
    [idx,C] = kmedoids(data,14);
    medoidsIndex = find(ismember(data,C,'rows')==1);
end
